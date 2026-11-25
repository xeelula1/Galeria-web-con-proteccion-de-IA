"""Escáner seguro de imágenes en input/ con validación por magic bytes y hash SHA-256."""

import hashlib
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

from pixelforge.config import resolve_safe_path, sanitize_filename
from pixelforge.models import ImageSource

JPEG_MAGIC_PREFIX = b"\xff\xd8\xff"
PNG_MAGIC_PREFIX = b"\x89PNG\r\n\x1a\n"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def detect_mime_type(file_path: Path) -> Literal["image/jpeg", "image/png"] | None:
    """Detecta el tipo MIME real leyendo los primeros 16 magic bytes del archivo."""
    try:
        with file_path.open("rb") as f:
            header = f.read(16)
    except OSError:
        return None

    if header.startswith(JPEG_MAGIC_PREFIX):
        return "image/jpeg"
    if header.startswith(PNG_MAGIC_PREFIX):
        return "image/png"
    return None


def compute_sha256(file_path: Path) -> str:
    """Calcula el hash SHA-256 de un archivo en bloques de 64 KB sin saturar la memoria."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verify_pillow_integrity(file_path: Path) -> None:
    """Verifica que Pillow pueda decodificar la estructura de la imagen sin estar corrupta."""
    with Image.open(file_path) as img:
        img.verify()
    with Image.open(file_path) as img:
        img.load()


def scan_input_directory(input_dir: Path) -> tuple[list[ImageSource], list[str]]:
    """Descubre y valida archivos JPG/PNG en input_dir sin modificar jamás los originales.

    Retorna:
        tuple[list[ImageSource], list[str]]: Fuentes válidas y lista de advertencias/errores.
    """
    sources: list[ImageSource] = []
    warnings: list[str] = []

    if not input_dir.exists() or not input_dir.is_dir():
        return sources, warnings

    resolved_base = input_dir.resolve()
    entries = sorted(resolved_base.iterdir(), key=lambda p: p.name.lower())

    for entry in entries:
        if entry.name.startswith("."):
            continue

        try:
            safe_name = sanitize_filename(entry.name)
            safe_path = resolve_safe_path(resolved_base, entry)
        except ValueError as exc:
            warnings.append(f"Archivo omitido por ruta insegura ({entry.name}): {exc}")
            continue

        if not safe_path.is_file():
            continue

        ext = safe_path.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue

        mime_type = detect_mime_type(safe_path)
        if mime_type is None:
            warnings.append(
                f"Archivo omitido '{safe_name}': firma binaria (magic bytes) inválida para JPG/PNG."
            )
            continue

        try:
            _verify_pillow_integrity(safe_path)
            sha256_hash = compute_sha256(safe_path)
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
            warnings.append(f"Archivo corrupto o ilegible omitido '{safe_name}': {exc}")
            continue

        sources.append(
            ImageSource(
                path=safe_path,
                filename=safe_name,
                mime_type=mime_type,
                sha256=sha256_hash,
            )
        )

    return sources, warnings
