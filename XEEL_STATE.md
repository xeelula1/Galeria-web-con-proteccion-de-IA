# XEEL_STATE.md — Bitácora de Estado y Memoria del Proyecto

## 📌 Estado General
- **Proyecto:** PixelForge (Galería Web con Protección de IA)
- **Repositorio Oficial:** `https://github.com/xeelula1/Galeria-web-con-proteccion-de-IA`
- **Rama Activa:** `main` (Sincronizada con `origin/main`)
- **Fase Actual:** V1.1 en Producción Local (Bloques 1 a 6 cerrados y consolidados vía *Auto Dream*)
- **Última Actualización:** 2026-11-24

## ⚡ Comandos Oficiales del Proyecto
- **Instalación:** `uv sync --python 3.12`
- **Ejecución (Online con Gemini):** `uv run pixelforge --serve --port 8000`
- **Ejecución (Modo Offline + Servidor Web):** `uv run pixelforge --offline --serve --port 8000`
- **Tests:** `uv run pytest`
- **Linter / Calidad:** `uv run ruff check .`
- **Build / Empaquetado:** `uv build`

## 🧠 Stack Tecnológico y Justificación
- **`uv` (0.13.3) + CPython 3.12.15:** Resolución determinista (`uv.lock`) con ruedas binarias estables para extensiones C/Rust.
- **`pydantic` (2.14.4):** Validación estricta en tiempo de ejecución (`AIDescription`) y protección de secretos con `SecretStr`.
- **`python-dotenv` (1.2.4):** Lectura aislada de `.env` (`dotenv_values`) sin contaminar el entorno del sistema operativo.
- **`pillow` (13.0.0):** Pipeline gráfico en memoria (`RGBA`/`RGB`), thumbnail `300x300`, viñeta radial, watermark `"© PixelForge"` y eliminación 100% de metadatos EXIF.
- **`google-genai` (3.6.1):** SDK oficial de Google GenAI (`gemini-2.5-flash`) con *Structured Outputs*, reintento acotado y redacción automática de credenciales en logs.
- **`jinja2` (3.1.6):** Motor de plantillas con `select_autoescape(("html", "htm", "xml", "j2"), default=True)` activo contra XSS.
- **`http.server` (`ThreadingHTTPServer`):** Servidor local enlazado estrictamente a `127.0.0.1` con soporte de subida interactiva `POST /upload`.
- **`ruff` (0.17.6) + `pytest` (9.2.0):** Linter/formateador y suite de 16 pruebas unitarias y de ciberseguridad.

## 📁 Estructura del Proyecto (Árbol de Archivos)
pixelforge/
├── .env.example              — Plantilla segura sin secretos reales (GEMINI_API_KEY=)
├── .gitignore                — Bloquea .env, input/, output/, .venv/, __pycache__/
├── .python-version           — Fija versión de intérprete a Python 3.12
├── pyproject.toml            — Configuración de uv, hatchling, dependencias, ruff y pytest
├── uv.lock                   — Lockfile determinista de dependencias congeladas
├── XEEL_RULESV3.md           — [SOLO LECTURA] Protocolo Maestro de Ingeniería: Metodología XEEL V3
├── XEEL_STATE.md             — [GESTIONADO] Bitácora de Estado y Memoria del Proyecto (Capa 2 y 3)
├── input/                    — [SOLO LECTURA] Imágenes originales del usuario (JPG/PNG)
├── output/                   — [GENERADO] Galería compilada (images/, thumbs/, index.html)
├── templates/
│   └── gallery.html.j2       — Plantilla HTML5/CSS3 Grid responsive con subida Drag & Drop, filtros, lightbox y CSP
├── tests/
│   ├── test_processor.py     — Tests de inmutabilidad SHA-256, 300x300, viñeta, watermark, EXIF y modos CMYK/P
│   ├── test_ai_describer.py  — Tests con mocks de Gemini API, modo offline, retry 429, JSON inválido y Zero-Leak
│   └── test_security.py      — Auditoría E2E: limpieza EXIF, Path Traversal, XSS, Zero-Leak, 127.0.0.1 y POST /upload
└── src/
    └── pixelforge/
        ├── __init__.py       — Inicialización y versión del paquete (0.1.0)
        ├── models.py         — Contratos de datos inmutables (@dataclass) y validados (Pydantic)
        ├── config.py         — Carga segura de .env (SecretStr) y defensa contra Path Traversal
        ├── scanner.py        — Escáner de input/ por magic bytes, integridad Pillow y hash SHA-256
        ├── processor.py      — Pipeline gráfico en memoria (resize, thumb 300x300, viñeta, watermark, 0 EXIF)
        ├── ai_describer.py   — Cliente aislado de Gemini (gemini-2.5-flash) con fallback y protección Zero-Leak
        ├── builder.py        — Compilador Jinja2 con autoescape forzado (.j2) hacia output/index.html
        └── cli.py            — Orquestador CLI, servidor local 127.0.0.1 y subida web segura (POST /upload)

## 🗄️ Esquema de Datos / Persistencia
- Arquitectura Zero-DB: artefactos estáticos en `output/images/`, `output/thumbs/` y `output/index.html`, preservando la inmutabilidad SHA-256 de `input/`.

## 🛠️ Módulos Completados y Verificados
- [x] **Bloque 1 (Base, Modelos y Configuración):** `pyproject.toml`, `.gitignore`, `.env.example`, `models.py`, `config.py`.
- [x] **Bloque 2 (Escáner y Motor Gráfico):** `scanner.py`, `processor.py`, `tests/test_processor.py` (4/4 tests).
- [x] **Bloque 3 (Módulo de Visión IA):** `ai_describer.py`, `tests/test_ai_describer.py` (5/5 tests).
- [x] **Bloque 4 (Generador de Galería Web):** `builder.py`, `templates/gallery.html.j2` con protección XSS y CSP.
- [x] **Bloque 5 (Orquestación CLI, Servidor Local y Auditoría):** `cli.py`, `tests/test_security.py`.
- [x] **Bloque 6 (Subida Web Interactiva `POST /upload`):** Subida Drag & Drop desde el navegador con validación de *magic bytes*, preservación de archivos existentes y recompilación automática (16/16 tests totales al 100%).

## 📋 Contratos de Datos Vigentes (Firmas de Interfaz)
- **`src/pixelforge/models.py`:** `AppConfig`, `ImageSource`, `ProcessedImage`, `AIDescription`, `GalleryItem`, `PipelineReport`
- **`src/pixelforge/config.py`:** `resolve_safe_path(base_dir, target_path) -> Path`, `sanitize_filename(filename) -> str`, `load_config(...) -> AppConfig`
- **`src/pixelforge/scanner.py`:** `detect_mime_type(file_path) -> Literal["image/jpeg", "image/png"] | None`, `compute_sha256(file_path) -> str`, `scan_input_directory(input_dir) -> tuple[list[ImageSource], list[str]]`
- **`src/pixelforge/processor.py`:** `apply_vignette(image, strength=0.65) -> Image.Image`, `apply_watermark(image, text="© PixelForge") -> Image.Image`, `process_image(source, config) -> ProcessedImage`
- **`src/pixelforge/ai_describer.py`:** `build_fallback_description(filename) -> AIDescription`, `sanitize_secret_from_text(text, secret) -> str`, `describe_image(processed, config, client=None, max_retries=1) -> AIDescription`
- **`src/pixelforge/builder.py`:** `create_gallery_item(processed, ai_desc) -> GalleryItem`, `collect_unique_tags(items) -> list[str]`, `create_jinja_environment(templates_dir) -> Environment`, `build_gallery(items, config, template_name="gallery.html.j2") -> Path`
- **`src/pixelforge/cli.py`:** `save_uploaded_image(input_dir, raw_filename, data) -> Path`, `run_pipeline(config, ai_client=None) -> PipelineReport`, `create_local_server(output_dir, port=8000, host="127.0.0.1", config=None) -> ThreadingHTTPServer`, `serve_gallery(...) -> None`, `main(argv=None) -> int`

## 🔒 Dependencias Congeladas
- `google-genai==3.6.1`
- `jinja2==3.1.6`
- `pillow==13.0.0`
- `pydantic==2.14.4`
- `python-dotenv==1.2.4`
- `pytest==9.2.0`
- `ruff==0.17.6`

## 🎯 Siguiente Paso Pendiente
- **Hito al reanudar:** Si se desea activar la visión IA real en local, crear `.env` con `GEMINI_API_KEY=<clave>` y ejecutar `uv run pixelforge --serve --port 8000` (o proponer un nuevo módulo bajo la Metodología XEEL V3).
