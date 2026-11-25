"""Motor gráfico en memoria: resize, thumbnail 300x300, viñeta, watermark y limpieza EXIF."""

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from pixelforge.config import resolve_safe_path, sanitize_filename
from pixelforge.models import AppConfig, ImageSource, ProcessedImage

_CANDIDATE_FONTS = (
    "arial.ttf",
    "segoeui.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",
)


def _load_watermark_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carga una fuente TTF del sistema o recurre a la fuente integrada de Pillow."""
    for font_name in _CANDIDATE_FONTS:
        try:
            return ImageFont.truetype(font_name, size=font_size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()


def apply_vignette(image: Image.Image, strength: float = 0.65) -> Image.Image:
    """Aplica un filtro de viñeta radial suave oscureciendo los bordes de la imagen en memoria."""
    rgba_img = image.convert("RGBA")
    width, height = rgba_img.size

    grid_size = 256
    mask_small = Image.new("L", (grid_size, grid_size), 0)
    center = (grid_size - 1) / 2.0
    max_dist = math.hypot(center, center)

    pixels: list[int] = []
    for y in range(grid_size):
        dy = y - center
        for x in range(grid_size):
            dx = x - center
            norm_dist = math.hypot(dx, dy) / max_dist
            factor = max(0.0, (norm_dist - 0.25) / 0.75)
            alpha = int(min(255.0, (factor**1.8) * 255.0 * strength))
            pixels.append(alpha)

    mask_small.putdata(pixels)
    full_mask = mask_small.resize((width, height), resample=Image.Resampling.BILINEAR)

    dark_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    black_layer = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    dark_overlay.paste(black_layer, (0, 0), full_mask)

    return Image.alpha_composite(rgba_img, dark_overlay)


def apply_watermark(image: Image.Image, text: str = "© PixelForge") -> Image.Image:
    """Estampa la marca de agua semitransparente en la esquina inferior derecha."""
    base_img = image.convert("RGBA")
    width, height = base_img.size

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(14, min(width, height) // 22)
    font = _load_watermark_font(font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    padding_x = max(12, width // 40)
    padding_y = max(12, height // 40)
    x = max(4, width - text_width - padding_x)
    y = max(4, height - text_height - padding_y)

    shadow_offset = max(1, font_size // 14)
    draw.text(
        (x + shadow_offset, y + shadow_offset),
        text,
        font=font,
        fill=(0, 0, 0, 150),
    )
    draw.text(
        (x, y),
        text,
        font=font,
        fill=(255, 255, 255, 195),
    )

    return Image.alpha_composite(base_img, overlay)


def _strip_exif_and_save(image: Image.Image, dest_path: Path, mime_type: str) -> None:
    """Guarda la imagen en dest_path garantizando cero metadatos EXIF y canales seguros."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = image.size

    if mime_type == "image/jpeg":
        rgba = image.convert("RGBA")
        clean_rgb = Image.new("RGB", (width, height), (0, 0, 0))
        clean_rgb.paste(rgba, mask=rgba.split()[3])
        clean_rgb.save(dest_path, format="JPEG", quality=90, optimize=True)
    else:
        rgba = image.convert("RGBA")
        clean_rgba = Image.new("RGBA", (width, height))
        clean_rgba.paste(rgba)
        clean_rgba.save(dest_path, format="PNG", optimize=True)


def _build_ai_preview_bytes(image: Image.Image, max_dim: int) -> bytes:
    """Genera una copia ligera JPEG en memoria (máx. max_dim px) para enviar a Gemini API."""
    preview = image.copy()
    preview.thumbnail((max_dim, max_dim), resample=Image.Resampling.LANCZOS)

    rgba = preview.convert("RGBA")
    clean_rgb = Image.new("RGB", rgba.size, (0, 0, 0))
    clean_rgb.paste(rgba, mask=rgba.split()[3])

    buffer = io.BytesIO()
    clean_rgb.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue()


def process_image(source: ImageSource, config: AppConfig) -> ProcessedImage:
    """Ejecuta el pipeline gráfico completo sobre una imagen sin modificar jamás input/."""
    safe_filename = sanitize_filename(source.filename)
    output_image_path = resolve_safe_path(config.images_dir, safe_filename)
    output_thumb_path = resolve_safe_path(config.thumbs_dir, safe_filename)

    with Image.open(source.path) as raw_img:
        transposed = ImageOps.exif_transpose(raw_img)
        working_img = transposed.convert("RGBA")

    if working_img.width > config.max_image_dim or working_img.height > config.max_image_dim:
        working_img.thumbnail(
            (config.max_image_dim, config.max_image_dim),
            resample=Image.Resampling.LANCZOS,
        )

    ai_preview_bytes = _build_ai_preview_bytes(working_img, config.ai_preview_dim)

    vignetted = apply_vignette(working_img)
    final_img = apply_watermark(vignetted, text=config.watermark_text)

    thumb_img = ImageOps.fit(
        final_img,
        config.thumb_size,
        method=Image.Resampling.LANCZOS,
    )

    _strip_exif_and_save(final_img, output_image_path, source.mime_type)
    _strip_exif_and_save(thumb_img, output_thumb_path, source.mime_type)

    return ProcessedImage(
        source_filename=safe_filename,
        output_image_path=output_image_path,
        output_thumb_path=output_thumb_path,
        width=final_img.width,
        height=final_img.height,
        thumb_size=thumb_img.size,
        ai_preview_bytes=ai_preview_bytes,
    )
