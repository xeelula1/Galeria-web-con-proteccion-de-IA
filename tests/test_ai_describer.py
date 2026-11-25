"""Tests unitarios con mocks para ai_describer.py (Bloque 3)."""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from pixelforge.ai_describer import describe_image
from pixelforge.models import AppConfig, ProcessedImage


def _make_dummy_config(
    tmp_path: Path,
    api_key: str | None = "AIzaSyDummySecretKeyForTests12345",
    offline: bool = False,
) -> AppConfig:
    return AppConfig(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        images_dir=tmp_path / "output" / "images",
        thumbs_dir=tmp_path / "output" / "thumbs",
        templates_dir=tmp_path / "templates",
        gemini_api_key=SecretStr(api_key) if api_key else None,
        offline=offline,
    )


def _make_dummy_processed(tmp_path: Path) -> ProcessedImage:
    return ProcessedImage(
        source_filename="sunset.jpg",
        output_image_path=tmp_path / "output" / "images" / "sunset.jpg",
        output_thumb_path=tmp_path / "output" / "thumbs" / "sunset.jpg",
        width=1200,
        height=800,
        thumb_size=(300, 300),
        ai_preview_bytes=b"\xff\xd8\xff\xe0dummy_jpeg_bytes",
    )


def test_describe_image_success_with_mock_client(tmp_path: Path) -> None:
    """Verifica el parseo exitoso de JSON estructurado devuelto por Gemini."""
    config = _make_dummy_config(tmp_path)
    processed = _make_dummy_processed(tmp_path)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "description": "Atardecer cálido sobre las montañas con cielo naranja.",
            "tags": ["Atardecer", "Montaña", "Naturaleza", "atardecer"],
        }
    )
    mock_client.models.generate_content.return_value = mock_response

    result = describe_image(processed, config, client=mock_client)

    assert result.is_fallback is False
    assert result.description == "Atardecer cálido sobre las montañas con cielo naranja."
    assert result.tags == ["atardecer", "montaña", "naturaleza"]
    mock_client.models.generate_content.assert_called_once()


def test_describe_image_offline_or_missing_key_uses_fallback(tmp_path: Path) -> None:
    """Comprueba que en modo --offline o sin API key no se llame a la red y actúe el fallback."""
    processed = _make_dummy_processed(tmp_path)
    mock_client = MagicMock()

    offline_cfg = _make_dummy_config(tmp_path, offline=True)
    res_offline = describe_image(processed, offline_cfg, client=mock_client)
    assert res_offline.is_fallback is True
    assert res_offline.tags == ["sin-etiqueta"]
    mock_client.models.generate_content.assert_not_called()

    no_key_cfg = _make_dummy_config(tmp_path, api_key=None, offline=False)
    res_no_key = describe_image(processed, no_key_cfg, client=mock_client)
    assert res_no_key.is_fallback is True
    assert res_no_key.tags == ["sin-etiqueta"]
    mock_client.models.generate_content.assert_not_called()


def test_describe_image_retries_once_on_network_error_then_succeeds(tmp_path: Path) -> None:
    """Verifica que ante un timeout o rate limit (429) reintente 1 vez y recupere si tiene éxito."""
    config = _make_dummy_config(tmp_path)
    processed = _make_dummy_processed(tmp_path)

    mock_client = MagicMock()
    good_response = MagicMock()
    good_response.text = json.dumps(
        {"description": "Bosque nublado al amanecer.", "tags": ["bosque", "niebla"]}
    )
    mock_client.models.generate_content.side_effect = [
        RuntimeError("429 Resource Exhausted: Rate limit exceeded"),
        good_response,
    ]

    result = describe_image(processed, config, client=mock_client, max_retries=1)

    assert result.is_fallback is False
    assert result.description == "Bosque nublado al amanecer."
    assert mock_client.models.generate_content.call_count == 2


def test_describe_image_malformed_json_falls_back_safely(tmp_path: Path) -> None:
    """Verifica que un JSON corrupto o fuera de esquema retorne fallback sin romper el pipeline."""
    config = _make_dummy_config(tmp_path)
    processed = _make_dummy_processed(tmp_path)

    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.text = "{not_valid_json: true"
    mock_client.models.generate_content.return_value = bad_response

    result = describe_image(processed, config, client=mock_client)

    assert result.is_fallback is True
    assert result.tags == ["sin-etiqueta"]


def test_zero_leak_policy_redacts_api_key_from_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Garantiza que si un error incluye la GEMINI_API_KEY, jamás se imprima en logs."""
    secret_value = "AIzaSySuperSecretKeyNeverLeak99999"
    config = _make_dummy_config(tmp_path, api_key=secret_value)
    processed = _make_dummy_processed(tmp_path)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ConnectionError(
        f"HTTPSConnectionPool error with key={secret_value} failed"
    )

    with caplog.at_level(logging.WARNING):
        result = describe_image(processed, config, client=mock_client, max_retries=0)

    assert result.is_fallback is True
    assert secret_value not in caplog.text
    assert "[REDACTED_API_KEY]" in caplog.text
