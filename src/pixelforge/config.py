"""Carga segura de configuración (.env) y validación de rutas contra Path Traversal."""

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr

from pixelforge.models import AppConfig


def resolve_safe_path(base_dir: Path, target_path: Path | str) -> Path:
    """Resuelve una ruta y verifica que permanezca estrictamente dentro de base_dir.

    Previene ataques de Path Traversal (ej. '../../etc/passwd' o enlaces simbólicos
    que apunten fuera del directorio base permitido).
    """
    resolved_base = base_dir.resolve()
    candidate = Path(target_path)
    if not candidate.is_absolute():
        resolved_target = (resolved_base / candidate).resolve()
    else:
        resolved_target = candidate.resolve()

    if not resolved_target.is_relative_to(resolved_base):
        raise ValueError(
            f"Violación de seguridad (Path Traversal): la ruta '{target_path}' "
            f"escapa del directorio base permitido."
        )
    return resolved_target


def sanitize_filename(filename: str) -> str:
    """Valida que un nombre de archivo sea simple y no contenga separadores de ruta."""
    clean_name = filename.strip()
    if (
        not clean_name
        or clean_name in {".", ".."}
        or "/" in clean_name
        or "\\" in clean_name
        or Path(clean_name).name != clean_name
    ):
        raise ValueError(f"Nombre de archivo inseguro o inválido (Path Traversal): '{filename}'")
    return clean_name


def load_config(
    base_dir: Path | None = None,
    offline: bool = False,
    env_file: Path | None = None,
    input_subdir: Path | str = "input",
    output_subdir: Path | str = "output",
    templates_subdir: Path | str = "templates",
) -> AppConfig:
    """Carga la configuración de la aplicación validando rutas y protegiendo GEMINI_API_KEY."""
    root_dir = (base_dir or Path.cwd()).resolve()

    input_dir = resolve_safe_path(root_dir, input_subdir)
    output_dir = resolve_safe_path(root_dir, output_subdir)
    images_dir = resolve_safe_path(output_dir, "images")
    thumbs_dir = resolve_safe_path(output_dir, "thumbs")
    templates_dir = resolve_safe_path(root_dir, templates_subdir)

    dotenv_path = env_file.resolve() if env_file else (root_dir / ".env")
    raw_key: str | None = None

    if dotenv_path.is_file():
        env_Map = dotenv_values(dotenv_path)
        raw_key = env_Map.get("GEMINI_API_KEY")

    if raw_key is None:
        raw_key = os.environ.get("GEMINI_API_KEY")

    clean_key = raw_key.strip() if raw_key else ""
    secret_key: SecretStr | None = SecretStr(clean_key) if clean_key else None

    return AppConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        images_dir=images_dir,
        thumbs_dir=thumbs_dir,
        templates_dir=templates_dir,
        gemini_api_key=secret_key,
        offline=offline,
    )
