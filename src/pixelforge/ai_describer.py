"""Cliente aislado de visión IA con Google GenAI (gemini-3.8-flash) y fallback automático."""

import json
import logging
import time
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, SecretStr, ValidationError

from pixelforge.models import AIDescription, AppConfig, ProcessedImage

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
)
VISION_PROMPT = (
    "Analiza esta imagen y devuelve un objeto JSON con:\n"
    "- 'description': descripción visual concisa y atractiva en español (máximo 280 caracteres).\n"
    "- 'tags': lista de entre 2 y 6 etiquetas cortas en español y en minúsculas."
)


class _GeminiVisionSchema(BaseModel):
    """Esquema interno enviado a Gemini Structured Outputs."""

    description: str = Field(..., min_length=1, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=6)


def build_fallback_description(filename: str) -> AIDescription:
    """Construye la descripción de respaldo para modo --offline, sin API key o error de red."""
    safe_desc = f"Imagen procesada por PixelForge ({filename})."[:300]
    return AIDescription(
        description=safe_desc,
        tags=["sin-etiqueta"],
        is_fallback=True,
    )


def sanitize_secret_from_text(text: str, secret: SecretStr | None) -> str:
    """Elimina cualquier aparición del valor secreto en logs o mensajes de excepción (Zero-Leak)."""
    if not text or secret is None:
        return text
    raw_secret = secret.get_secret_value()
    if not raw_secret:
        return text
    return text.replace(raw_secret, "[REDACTED_API_KEY]")


def _parse_and_normalize_response(raw_text: str) -> AIDescription:
    """Valida y normaliza la respuesta JSON de Gemini según el contrato AIDescription."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Respuesta vacía de Gemini API.")

    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("El JSON de respuesta no es un objeto válido.")

    raw_desc = payload.get("description")
    if not isinstance(raw_desc, str) or not raw_desc.strip():
        raise ValueError("Campo 'description' ausente o inválido en respuesta de IA.")

    clean_desc = raw_desc.strip()[:300]

    raw_tags = payload.get("tags", [])
    if not isinstance(raw_tags, list):
        raise ValueError("Campo 'tags' no es una lista.")

    normalized_tags: list[str] = []
    for item in raw_tags:
        if isinstance(item, str):
            tag = item.strip().lower()
            if tag and tag not in normalized_tags:
                normalized_tags.append(tag)
        if len(normalized_tags) >= 6:
            break

    if not normalized_tags:
        normalized_tags = ["general"]

    return AIDescription(
        description=clean_desc,
        tags=normalized_tags,
        is_fallback=False,
    )


def describe_image(
    processed: ProcessedImage,
    config: AppConfig,
    client: Any | None = None,
    max_retries: int = 1,
) -> AIDescription:
    """Genera descripción y etiquetas usando gemini-3.8-flash o aplica fallback seguro."""
    if config.offline or config.gemini_api_key is None:
        return build_fallback_description(processed.source_filename)

    if not processed.ai_preview_bytes:
        logger.warning(
            "Preview en memoria vacío para '%s'; aplicando fallback.",
            processed.source_filename,
        )
        return build_fallback_description(processed.source_filename)

    active_client = client
    if active_client is None:
        try:
            active_client = genai.Client(api_key=config.gemini_api_key.get_secret_value())
        except Exception as exc:
            safe_msg = sanitize_secret_from_text(str(exc), config.gemini_api_key)
            logger.warning(
                "No se pudo inicializar el cliente Gemini para '%s': %s",
                processed.source_filename,
                safe_msg,
            )
            return build_fallback_description(processed.source_filename)

    image_part = types.Part.from_bytes(
        data=processed.ai_preview_bytes,
        mime_type="image/jpeg",
    )
    gen_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_GeminiVisionSchema,
        temperature=0.2,
    )

    attempts = max(1, max_retries + 1)
    candidate_models = FALLBACK_MODELS if client is None else (DEFAULT_MODEL,) * attempts
    total_tries = len(candidate_models) if client is None else attempts

    for attempt, model_name in enumerate(candidate_models[:total_tries], start=1):
        try:
            response = active_client.models.generate_content(
                model=model_name,
                contents=[image_part, VISION_PROMPT],
                config=gen_config,
            )
            raw_text = getattr(response, "text", None) or ""
            return _parse_and_normalize_response(raw_text)
        except (json.JSONDecodeError, ValidationError, ValueError) as parse_exc:
            safe_msg = sanitize_secret_from_text(str(parse_exc), config.gemini_api_key)
            logger.warning(
                "Respuesta JSON inválida de Gemini (%s) para '%s': %s",
                model_name,
                processed.source_filename,
                safe_msg,
            )
            return build_fallback_description(processed.source_filename)
        except Exception as net_exc:
            safe_msg = sanitize_secret_from_text(str(net_exc), config.gemini_api_key)
            if attempt < total_tries:
                logger.warning(
                    "Fallo temporal en Gemini (%s) para '%s' (intento %d/%d): %s. "
                    "Saltando al siguiente modelo disponible...",
                    model_name,
                    processed.source_filename,
                    attempt,
                    total_tries,
                    safe_msg,
                )
                if client is None:
                    time.sleep(1.0)
                continue
            logger.warning(
                "Fallo definitivo en Gemini para '%s' tras %d intento(s): %s. Usando fallback.",
                processed.source_filename,
                total_tries,
                safe_msg,
            )

    return build_fallback_description(processed.source_filename)
