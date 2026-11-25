"""Tests unitarios para scanner.py y processor.py (Bloque 2)."""

from pathlib import Path

from PIL import Image

from pixelforge.config import load_config
from pixelforge.processor import apply_vignette, apply_watermark, process_image
from pixelforge.scanner import compute_sha256, scan_input_directory


def _create_sample_jpeg_with_exif(path: Path, size: tuple[int, int] = (800, 600)) -> None:
    """Crea un archivo JPEG de prueba con metadatos EXIF simulados (cámara, GPS, autor)."""
    img = Image.new("RGB", size, color=(120, 160, 220))
    exif = img.getexif()
    exif[0x010F] = "PixelForgeTestCamera"  # Make
    exif[0x0110] = "ModelX-Pro"  # Model
    exif[0x013B] = "SecretAuthorName"  # Artist
    img.save(path, format="JPEG", exif=exif.tobytes(), quality=95)


def test_input_immutability_and_processing_dimensions(tmp_path: Path) -> None:
    """Verifica que input/ quede intacto (SHA-256), thumb sea 300x300 y se limpie EXIF."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    img_path = input_dir / "photo_large.jpg"
    _create_sample_jpeg_with_exif(img_path, size=(2400, 1600))

    hash_before = compute_sha256(img_path)

    config = load_config(base_dir=tmp_path, offline=True)
    sources, warnings = scan_input_directory(config.input_dir)

    assert len(warnings) == 0
    assert len(sources) == 1
    assert sources[0].sha256 == hash_before

    result = process_image(sources[0], config)

    hash_after = compute_sha256(img_path)
    assert hash_before == hash_after, "El archivo original en input/ fue modificado."

    assert result.width == 1920
    assert result.height == 1280
    assert result.thumb_size == (300, 300)
    assert len(result.ai_preview_bytes) > 0

    with Image.open(result.output_thumb_path) as thumb:
        assert thumb.size == (300, 300)
        assert len(thumb.getexif()) == 0

    with Image.open(result.output_image_path) as out_img:
        assert out_img.size == (1920, 1280)
        assert len(out_img.getexif()) == 0


def test_vignette_and_watermark_modify_pixels() -> None:
    """Comprueba que la viñeta oscurezca los bordes y el watermark modifique la imagen."""
    base = Image.new("RGBA", (400, 400), (200, 200, 200, 255))

    vignetted = apply_vignette(base, strength=0.7)
    center_pixel = vignetted.getpixel((200, 200))
    corner_pixel = vignetted.getpixel((2, 2))
    assert corner_pixel[0] < center_pixel[0], "La viñeta debe oscurecer las esquinas."

    watermarked = apply_watermark(base, text="© PixelForge")
    assert watermarked.tobytes() != base.tobytes(), "El watermark debe alterar los píxeles."


def test_scanner_skips_corrupt_and_fake_magic_bytes(tmp_path: Path) -> None:
    """Verifica que archivos falsos (.jpg con texto) o truncados se omitan sin detener el lote."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    fake_jpg = input_dir / "fake_script.jpg"
    fake_jpg.write_bytes(b"#!/bin/bash\necho 'not an image'")

    corrupt_png = input_dir / "corrupt.png"
    corrupt_png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00truncado_invalido")

    valid_png = input_dir / "valid.png"
    Image.new("RGBA", (500, 400), (80, 180, 120, 255)).save(valid_png, format="PNG")

    sources, warnings = scan_input_directory(input_dir)

    assert len(sources) == 1
    assert sources[0].filename == "valid.png"
    assert sources[0].mime_type == "image/png"
    assert len(warnings) == 2


def test_special_color_modes_cmyk_palette_rgba_as_jpeg(tmp_path: Path) -> None:
    """Comprueba que imágenes en modos CMYK y P (paleta) se procesen sin crashear al guardar."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    cmyk_jpg = input_dir / "cmyk_photo.jpg"
    Image.new("CMYK", (640, 480), (20, 40, 60, 10)).save(cmyk_jpg, format="JPEG")

    palette_png = input_dir / "palette.png"
    Image.new("P", (640, 480), 12).save(palette_png, format="PNG")

    config = load_config(base_dir=tmp_path, offline=True)
    sources, warnings = scan_input_directory(config.input_dir)

    assert len(warnings) == 0
    assert len(sources) == 2

    for src in sources:
        processed = process_image(src, config)
        assert processed.output_image_path.is_file()
        assert processed.output_thumb_path.is_file()
        with Image.open(processed.output_thumb_path) as thumb:
            assert thumb.size == (300, 300)
