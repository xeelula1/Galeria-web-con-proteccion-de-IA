"""Compilador de galería web estática con Jinja2 y autoescape estricto contra XSS."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pixelforge.config import resolve_safe_path, sanitize_filename
from pixelforge.models import AIDescription, AppConfig, GalleryItem, ProcessedImage


def create_gallery_item(processed: ProcessedImage, ai_desc: AIDescription) -> GalleryItem:
    """Construye un GalleryItem validando rutas relativas POSIX limpias para el navegador."""
    safe_name = sanitize_filename(processed.source_filename)
    return GalleryItem(
        filename=safe_name,
        image_rel_path=f"images/{safe_name}",
        thumb_rel_path=f"thumbs/{safe_name}",
        description=ai_desc.description,
        tags=list(ai_desc.tags),
        width=processed.width,
        height=processed.height,
    )


def collect_unique_tags(items: list[GalleryItem]) -> list[str]:
    """Extrae y ordena alfabéticamente todas las etiquetas únicas presentes en la galería."""
    unique: set[str] = set()
    for item in items:
        for tag in item.tags:
            clean_tag = tag.strip().lower()
            if clean_tag:
                unique.add(clean_tag)
    return sorted(unique)


def create_jinja_environment(templates_dir: Path) -> Environment:
    """Configura el entorno Jinja2 con autoescape forzado incluso para extensiones .j2."""
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(
            enabled_extensions=("html", "htm", "xml", "j2"),
            default_for_string=True,
            default=True,
        ),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_gallery(
    items: list[GalleryItem],
    config: AppConfig,
    template_name: str = "gallery.html.j2",
) -> Path:
    """Compila la galería HTML estática en output/index.html con protección XSS."""
    safe_template_name = sanitize_filename(template_name)
    template_path = resolve_safe_path(config.templates_dir, safe_template_name)
    if not template_path.is_file():
        raise FileNotFoundError(f"No se encontró la plantilla Jinja2 en: {template_path}")

    output_index_path = resolve_safe_path(config.output_dir, "index.html")
    output_index_path.parent.mkdir(parents=True, exist_ok=True)

    env = create_jinja_environment(config.templates_dir)
    template = env.get_template(safe_template_name)

    all_tags = collect_unique_tags(items)
    rendered_html = template.render(
        items=items,
        all_tags=all_tags,
        total_count=len(items),
        watermark_text=config.watermark_text,
    )

    output_index_path.write_text(rendered_html, encoding="utf-8")
    return output_index_path
