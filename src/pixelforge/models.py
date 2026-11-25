"""Contratos de datos estrictos para el pipeline PixelForge (Arquitectura XEEL V3)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


@dataclass(frozen=True)
class AppConfig:
    input_dir: Path
    output_dir: Path
    images_dir: Path
    thumbs_dir: Path
    templates_dir: Path
    gemini_api_key: SecretStr | None
    offline: bool = False
    thumb_size: tuple[int, int] = (300, 300)
    max_image_dim: int = 1920
    ai_preview_dim: int = 1024
    watermark_text: str = "© PixelForge"


@dataclass(frozen=True)
class ImageSource:
    path: Path
    filename: str
    mime_type: Literal["image/jpeg", "image/png"]
    sha256: str


@dataclass(frozen=True)
class ProcessedImage:
    source_filename: str
    output_image_path: Path
    output_thumb_path: Path
    width: int
    height: int
    thumb_size: tuple[int, int]
    ai_preview_bytes: bytes


class AIDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., min_length=1, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=6)
    is_fallback: bool = False


@dataclass(frozen=True)
class GalleryItem:
    filename: str
    image_rel_path: str
    thumb_rel_path: str
    description: str
    tags: list[str]
    width: int
    height: int


@dataclass(frozen=True)
class PipelineReport:
    total_found: int
    processed_count: int
    skipped_count: int
    errors: list[str]
    index_html_path: Path | None
