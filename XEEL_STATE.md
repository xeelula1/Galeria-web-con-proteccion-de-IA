# XEEL_STATE.md — Bitácora de Estado y Memoria del Proyecto

## 📌 Estado General
- **Proyecto:** PixelForge
- **Rama Activa:** feat/bloque-6-web-upload (Release Candidate 1.1)
- **Fase Actual:** Bloques 1 a 6 completados y verificados al 100%
- **Última Actualización:** 2026-11-24

## ⚡ Comandos Oficiales del Proyecto
- **Instalación:** `uv sync --python 3.12`
- **Ejecución (Online con Gemini):** `uv run pixelforge`
- **Ejecución (Modo Offline):** `uv run pixelforge --offline`
- **Ejecución + Servidor Local (`127.0.0.1:8000`):** `uv run pixelforge --offline --serve --port 8000`
- **Tests:** `uv run pytest`
- **Linter / Calidad:** `uv run ruff check .`
- **Build / Empaquetado:** `uv build`

## 🧠 Stack Tecnológico y Justificación
- **`uv` (0.13.3) + CPython 3.12.15:** Resolución ultrarrápida y determinista (`uv.lock`) con soporte de ruedas binarias estables para extensiones C/Rust.
- **`pydantic` (2.14.4):** Validación estricta en tiempo de ejecución (`AIDescription` con `extra="forbid"`) y protección de credenciales en memoria/logs mediante `SecretStr`.
- **`python-dotenv` (1.2.4):** Lectura aislada de `.env` (`dotenv_values`) sin contaminar variables globales del sistema operativo.
- **`pillow` (13.0.0):** Procesamiento gráfico en memoria (`RGBA`/`RGB`), generación de thumbnails (`ImageOps.fit`), máscara radial de viñeta optimizada, watermark con fallback `ImageFont.load_default(size=...)` y limpieza total de metadatos EXIF.
- **`google-genai` (3.6.1):** SDK oficial actual de Google GenAI para visión multimodal con `gemini-2.5-flash`, soporte nativo de *Structured Outputs*, reintento acotado y redacción automática de secretos en logs.
- **`jinja2` (3.1.6):** Motor de plantillas configurado con `select_autoescape(("html", "htm", "xml", "j2"), default=True)` activo para mitigar XSS por diseño.
- **`http.server` (`ThreadingHTTPServer`):** Servidor local enlazado estrictamente a `127.0.0.1` para previsualización segura sin exposición en interfaces externas.
- **`ruff` (0.17.6) + `pytest` (9.2.0):** Linter/formateador de alto rendimiento y suite de pruebas unitarias/seguridad con fixtures temporales y mocks.

## 📁 Estructura del Proyecto (Árbol de Archivos)
pixelforge/
├── .env.example              — Plantilla segura sin secretos reales (GEMINI_API_KEY=)
├── .gitignore                — Bloquea .env, input/, output/, .venv/, __pycache__/
├── .python-version           — Fija versión de intérprete a Python 3.12
├── pyproject.toml            — Configuración de uv, hatchling, dependencias, ruff y pytest
├── uv.lock                   — Lockfile determinista de dependencias congeladas
├── XEEL_RULESV3.md           — [SOLO LECTURA] Protocolo Maestro de Ingeniería: Metodología XEEL V3
├── XEEL_STATE.md             — [GESTIONADO] Bitácora de Estado y Memoria del Proyecto
├── input/                    — [SOLO LECTURA] Imágenes originales JPG/PNG
├── output/                   — [GENERADO] Artefactos compilados
│   ├── images/               — Imágenes procesadas (viñeta + watermark, 0 EXIF)
│   ├── thumbs/               — Thumbnails exactos de 300x300 px (0 EXIF)
│   └── index.html            — Galería web estática responsive
├── templates/
│   └── gallery.html.j2       — Plantilla HTML5/CSS3 Grid responsive con filtros, lightbox y CSP estricta
├── tests/
│   ├── test_processor.py     — Tests de inmutabilidad SHA-256, 300x300, viñeta, watermark, EXIF y modos CMYK/P
│   ├── test_ai_describer.py  — Tests con mocks de Gemini API, modo offline, retry 429, JSON inválido y Zero-Leak
│   └── test_security.py      — Auditoría E2E: limpieza EXIF, Path Traversal, XSS, Zero-Leak y servidor 127.0.0.1
└── src/
    └── pixelforge/
        ├── __init__.py       — Inicialización y versión del paquete (0.1.0)
        ├── models.py         — Contratos de datos inmutables (@dataclass) y validados (Pydantic)
        ├── config.py         — Carga segura de .env (SecretStr) y defensa contra Path Traversal
        ├── scanner.py        — Escáner de input/ por magic bytes, integridad Pillow y hash SHA-256
        ├── processor.py      — Pipeline gráfico en memoria (resize, thumb 300x300, viñeta, watermark, 0 EXIF)
        ├── ai_describer.py   — Cliente aislado de Gemini (gemini-2.5-flash) con fallback y protección Zero-Leak
        ├── builder.py        — Compilador Jinja2 con autoescape forzado (.j2) hacia output/index.html
        └── cli.py            — Orquestador del pipeline CLI (--offline, --serve, --port) y servidor 127.0.0.1

## 🗄️ Esquema de Datos / Persistencia
- Sin base de datos (Zero-DB architecture). Persistencia basada en artefactos estáticos en `output/images/`, `output/thumbs/` y `output/index.html`, con inmutabilidad garantizada sobre `input/`.

## 🛠️ Módulos Completados y Verificados
- [x] **Bloque 1 (Base, Modelos y Configuración):** Inicialización con `uv`, `.gitignore`, `.env.example`, `pyproject.toml`, contratos estrictos en `src/pixelforge/models.py` y carga segura con prevención de *Path Traversal* en `src/pixelforge/config.py`.
- [x] **Bloque 2 (Escáner y Motor Gráfico):** Implementación de `src/pixelforge/scanner.py`, `src/pixelforge/processor.py` y verificación con `tests/test_processor.py` (4/4 tests pasando).
- [x] **Bloque 3 (Módulo de Visión IA):** Implementación de `src/pixelforge/ai_describer.py` y verificación con `tests/test_ai_describer.py` (5/5 tests pasando).
- [x] **Bloque 4 (Generador de Galería Web):** Implementación de `src/pixelforge/builder.py` y `templates/gallery.html.j2` verificado contra XSS.
- [x] **Bloque 5 (Orquestación CLI, Servidor Local y Auditoría):** Implementación de `src/pixelforge/cli.py` y `tests/test_security.py` (6/6 tests de seguridad pasando; 15/15 tests totales pasando al 100%, 0 advertencias de `ruff`, servidor HTTP verificado en `http://127.0.0.1:8000`).
- [x] **Bloque 6 (Subida Web Interactiva `POST /upload`):** Implementación de `save_uploaded_image` y endpoint `POST /upload` en `src/pixelforge/cli.py`, zona de subida Drag & Drop en `templates/gallery.html.j2` y test de seguridad `test_security_web_upload_validates_magic_bytes_and_preserves_existing` (16/16 tests pasando al 100%).

## 📋 Contratos de Datos Vigentes (Firmas de Interfaz)
- **Modelos (`src/pixelforge/models.py`):**
  - `AppConfig`, `ImageSource`, `ProcessedImage`, `AIDescription`, `GalleryItem`, `PipelineReport`
- **Configuración (`src/pixelforge/config.py`):**
  - `resolve_safe_path(base_dir: Path, target_path: Path | str) -> Path`
  - `sanitize_filename(filename: str) -> str`
  - `load_config(...) -> AppConfig`
- **Escáner (`src/pixelforge/scanner.py`):**
  - `detect_mime_type(file_path: Path) -> Literal["image/jpeg", "image/png"] | None`
  - `compute_sha256(file_path: Path) -> str`
  - `scan_input_directory(input_dir: Path) -> tuple[list[ImageSource], list[str]]`
- **Motor Gráfico (`src/pixelforge/processor.py`):**
  - `apply_vignette(image: Image.Image, strength: float = 0.65) -> Image.Image`
  - `apply_watermark(image: Image.Image, text: str = "© PixelForge") -> Image.Image`
  - `process_image(source: ImageSource, config: AppConfig) -> ProcessedImage`
- **Visión IA (`src/pixelforge/ai_describer.py`):**
  - `build_fallback_description(filename: str) -> AIDescription`
  - `sanitize_secret_from_text(text: str, secret: SecretStr | None) -> str`
  - `describe_image(processed: ProcessedImage, config: AppConfig, client: Any | None = None, max_retries: int = 1) -> AIDescription`
- **Compilador Web (`src/pixelforge/builder.py`):**
  - `create_gallery_item(processed: ProcessedImage, ai_desc: AIDescription) -> GalleryItem`
  - `collect_unique_tags(items: list[GalleryItem]) -> list[str]`
  - `create_jinja_environment(templates_dir: Path) -> Environment`
  - `build_gallery(items: list[GalleryItem], config: AppConfig, template_name: str = "gallery.html.j2") -> Path`
- **Orquestador CLI (`src/pixelforge/cli.py`):**
  - `run_pipeline(config: AppConfig, ai_client: Any | None = None) -> PipelineReport`
  - `create_local_server(output_dir: Path, port: int = 8000, host: str = "127.0.0.1") -> ThreadingHTTPServer`
  - `serve_gallery(output_dir: Path, port: int = 8000, host: str = "127.0.0.1") -> None`
  - `main(argv: list[str] | None = None) -> int`

## 🔒 Dependencias Congeladas
- `google-genai==3.6.1`
- `jinja2==3.1.6`
- `pillow==13.0.0`
- `pydantic==2.14.4`
- `python-dotenv==1.2.4`
- `pytest==9.2.0`
- `ruff==0.17.6`

## 🎯 Siguiente Paso Pendiente
- Proyecto **PixelForge** completado y auditado en sus 5 bloques. Listo para uso en producción local o protocolo de cierre de sesión (*Auto Dream*).
