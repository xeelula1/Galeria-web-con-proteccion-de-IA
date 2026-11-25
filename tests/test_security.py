"""Suite de auditoría de ciberseguridad y resiliencia End-to-End (Bloque 5)."""

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from pixelforge.builder import build_gallery
from pixelforge.cli import create_local_server, main, run_pipeline, save_uploaded_image
from pixelforge.config import load_config, resolve_safe_path, sanitize_filename
from pixelforge.models import GalleryItem
from pixelforge.scanner import compute_sha256


def _copy_template_to_tmp(tmp_path: Path) -> None:
    """Copia la plantilla oficial gallery.html.j2 al entorno temporal de pruebas."""
    project_root = Path(__file__).resolve().parent.parent
    src_tpl = project_root / "templates" / "gallery.html.j2"
    dst_dir = tmp_path / "templates"
    dst_dir.mkdir(parents=True, exist_ok=True)
    (dst_dir / "gallery.html.j2").write_text(
        src_tpl.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_security_exif_stripped_and_input_immutable_end_to_end(tmp_path: Path) -> None:
    """Verifica que el pipeline E2E elimine 100% de EXIF (GPS/Autor) y no altere input/."""
    _copy_template_to_tmp(tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    img_path = input_dir / "gps_photo.jpg"
    img = Image.new("RGB", (900, 700), (60, 120, 190))
    exif = img.getexif()
    exif[0x010F] = "ConfidentialCamera"
    exif[0x0110] = "ModelSecretGPS"
    exif[0x013B] = "PrivateUserGPS"
    img.save(img_path, format="JPEG", exif=exif.tobytes())

    original_hash = compute_sha256(img_path)

    config = load_config(base_dir=tmp_path, offline=True)
    report = run_pipeline(config)

    assert report.processed_count == 1
    assert report.index_html_path is not None
    assert report.index_html_path.is_file()
    assert compute_sha256(img_path) == original_hash

    out_img_path = config.images_dir / "gps_photo.jpg"
    out_thumb_path = config.thumbs_dir / "gps_photo.jpg"

    with Image.open(out_img_path) as out_img:
        assert len(out_img.getexif()) == 0

    with Image.open(out_thumb_path) as out_thumb:
        assert out_thumb.size == (300, 300)
        assert len(out_thumb.getexif()) == 0


def test_security_path_traversal_prevention(tmp_path: Path) -> None:
    """Verifica que cualquier intento de escapar del directorio base sea bloqueado."""
    with pytest.raises(ValueError, match="Path Traversal"):
        resolve_safe_path(tmp_path, "../../etc/passwd")

    with pytest.raises(ValueError, match="Path Traversal"):
        resolve_safe_path(tmp_path, "../outside_folder")

    for malicious_name in ["../secret.jpg", "..\\secret.jpg", "sub/file.png", "..", "."]:
        with pytest.raises(ValueError, match="Path Traversal"):
            sanitize_filename(malicious_name)


def test_security_xss_payloads_escaped_in_compiled_html(tmp_path: Path) -> None:
    """Comprueba que payloads XSS en descripción o etiquetas queden 100% escapados."""
    _copy_template_to_tmp(tmp_path)
    config = load_config(base_dir=tmp_path, offline=True)

    malicious_item = GalleryItem(
        filename="photo.jpg",
        image_rel_path="images/photo.jpg",
        thumb_rel_path="thumbs/photo.jpg",
        description='<script>alert("XSS_DESC")</script><img src=x onerror=alert(1)>',
        tags=['"><script>alert("XSS_TAG")</script>', "seguridad"],
        width=800,
        height=600,
    )

    index_path = build_gallery([malicious_item], config)
    html = index_path.read_text(encoding="utf-8")

    assert '<script>alert("XSS_DESC")</script>' not in html
    assert '<script>alert("XSS_TAG")</script>' not in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;script&gt;alert(" in html
    assert "innerHTML" not in html


def test_security_zero_leak_policy_and_gitignore(tmp_path: Path) -> None:
    """Verifica que GEMINI_API_KEY no se filtre en repr(), HTML ni logs, y .gitignore sea seguro."""
    _copy_template_to_tmp(tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    Image.new("RGB", (400, 400), (100, 150, 200)).save(input_dir / "sample.jpg", format="JPEG")

    secret_key = "AIzaSyTopSecretCredentialDoNotLeak777"
    env_file = tmp_path / ".env"
    env_file.write_text(f"GEMINI_API_KEY={secret_key}\n", encoding="utf-8")

    config = load_config(base_dir=tmp_path, env_file=env_file, offline=False)

    assert secret_key not in repr(config)
    assert secret_key not in str(config)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({"description": "Foto segura.", "tags": ["seguro"]})
    mock_client.models.generate_content.return_value = mock_resp

    report = run_pipeline(config, ai_client=mock_client)
    assert report.index_html_path is not None
    html_content = report.index_html_path.read_text(encoding="utf-8")
    assert secret_key not in html_content

    project_root = Path(__file__).resolve().parent.parent
    gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
    for required_rule in [".env", "input/", "output/", ".venv/"]:
        assert required_rule in gitignore_text


def test_security_local_server_restricted_to_localhost(tmp_path: Path) -> None:
    """Comprueba que el servidor rechace 0.0.0.0 y solo enlace a 127.0.0.1."""
    with pytest.raises(ValueError, match="127.0.0.1"):
        create_local_server(tmp_path, port=8000, host="0.0.0.0")

    with pytest.raises(ValueError, match="127.0.0.1"):
        create_local_server(tmp_path, port=8000, host="192.168.1.10")

    with pytest.raises(ValueError, match="rango seguro"):
        create_local_server(tmp_path, port=80, host="127.0.0.1")

    with create_local_server(tmp_path, port=0, host="127.0.0.1") as server:
        assert server.server_address[0] == "127.0.0.1"


def test_empty_input_directory_returns_clean_exit_code(tmp_path: Path) -> None:
    """Verifica que si input/ está vacío, CLI retorne código 1 y no cree un index.html roto."""
    _copy_template_to_tmp(tmp_path)
    (tmp_path / "input").mkdir()

    exit_code = main(["--offline", "--base-dir", str(tmp_path)])
    assert exit_code == 1
    assert not (tmp_path / "output" / "index.html").exists()


def test_security_web_upload_validates_magic_bytes_and_preserves_existing(
    tmp_path: Path,
) -> None:
    """Comprueba que save_uploaded_image valide magic bytes, limpie nombres y no sobrescriba."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    buf = io.BytesIO()
    Image.new("RGB", (500, 400), (90, 140, 210)).save(buf, format="JPEG")
    valid_jpeg_bytes = buf.getvalue()

    first_path = save_uploaded_image(input_dir, "../../mi foto.jpg", valid_jpeg_bytes)
    assert first_path.parent == input_dir.resolve()
    assert first_path.name == "mi_foto.jpg"
    first_hash = compute_sha256(first_path)

    # Subir otra imagen con el mismo nombre jamás debe sobrescribir el archivo original
    buf2 = io.BytesIO()
    Image.new("RGB", (600, 600), (200, 100, 50)).save(buf2, format="JPEG")
    second_path = save_uploaded_image(input_dir, "mi foto.jpg", buf2.getvalue())
    assert second_path.name == "mi_foto_1.jpg"
    assert compute_sha256(first_path) == first_hash

    # Subir un script falso con extensión .jpg debe ser rechazado antes de tocar disco
    with pytest.raises(ValueError, match="magic bytes"):
        save_uploaded_image(input_dir, "exploit.jpg", b"<script>alert(1)</script>")

