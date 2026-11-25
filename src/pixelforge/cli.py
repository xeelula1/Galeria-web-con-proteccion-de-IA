"""Punto de entrada CLI, orquestador del pipeline PixelForge y servidor local 127.0.0.1."""

import argparse
import functools
import io
import json
import re
import sys
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from pixelforge.ai_describer import describe_image, sanitize_secret_from_text
from pixelforge.builder import build_gallery, create_gallery_item
from pixelforge.config import load_config, resolve_safe_path, sanitize_filename
from pixelforge.models import AppConfig, GalleryItem, PipelineReport
from pixelforge.processor import process_image
from pixelforge.scanner import JPEG_MAGIC_PREFIX, PNG_MAGIC_PREFIX, scan_input_directory

LOCALHOST_BIND = "127.0.0.1"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB máximo por imagen
_PIPELINE_LOCK = threading.Lock()


def _normalize_upload_filename(raw_filename: str, is_png: bool) -> str:
    """Normaliza un nombre de archivo subido, eliminando rutas y caracteres peligrosos."""
    base_name = Path(raw_filename.replace("\\", "/")).name.strip()
    if not base_name:
        base_name = "upload.png" if is_png else "upload.jpg"

    stem = Path(base_name).stem
    clean_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_") or "imagen"
    ext = ".png" if is_png else ".jpg"
    return sanitize_filename(f"{clean_stem[:60]}{ext}")


def save_uploaded_image(input_dir: Path, raw_filename: str, data: bytes) -> Path:
    """Valida magic bytes en memoria y guarda en input/ sin sobrescribir originales."""
    if not data:
        raise ValueError("El archivo subido está vacío.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"El archivo excede el tamaño máximo permitido ({MAX_UPLOAD_BYTES} bytes)."
        )

    if data.startswith(JPEG_MAGIC_PREFIX):
        is_png = False
    elif data.startswith(PNG_MAGIC_PREFIX):
        is_png = True
    else:
        raise ValueError(
            "Formato inválido: solo se permiten imágenes JPG o PNG reales (magic bytes)."
        )

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise ValueError(f"El archivo de imagen está corrupto o es inválido: {exc}") from exc

    input_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _normalize_upload_filename(raw_filename, is_png=is_png)
    candidate_path = resolve_safe_path(input_dir, safe_name)

    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    counter = 1
    while candidate_path.exists():
        collision_name = sanitize_filename(f"{stem}_{counter}{suffix}")
        candidate_path = resolve_safe_path(input_dir, collision_name)
        counter += 1

    candidate_path.write_bytes(data)
    return candidate_path


def run_pipeline(config: AppConfig, ai_client: Any | None = None) -> PipelineReport:
    """Ejecuta el pipeline completo: escaneo -> motor gráfico -> visión IA -> compilación HTML."""
    sources, scan_warnings = scan_input_directory(config.input_dir)
    errors: list[str] = list(scan_warnings)
    skipped_count = len(scan_warnings)

    if not sources:
        if not config.input_dir.exists():
            errors.append(f"El directorio de entrada no existe: {config.input_dir}")
        else:
            errors.append(f"No se encontraron imágenes JPG/PNG válidas en: {config.input_dir}")
        return PipelineReport(
            total_found=0,
            processed_count=0,
            skipped_count=skipped_count,
            errors=errors,
            index_html_path=None,
        )

    gallery_items: list[GalleryItem] = []

    for source in sources:
        try:
            processed = process_image(source, config)
            ai_desc = describe_image(processed, config, client=ai_client)
            item = create_gallery_item(processed, ai_desc)
            gallery_items.append(item)
        except PermissionError as perm_exc:
            target = perm_exc.filename or str(config.output_dir)
            errors.append(f"Error crítico de permisos de escritura en '{target}': {perm_exc}")
            return PipelineReport(
                total_found=len(sources),
                processed_count=len(gallery_items),
                skipped_count=skipped_count + (len(sources) - len(gallery_items)),
                errors=errors,
                index_html_path=None,
            )
        except Exception as exc:
            safe_err = sanitize_secret_from_text(str(exc), config.gemini_api_key)
            errors.append(f"Error al procesar '{source.filename}': {safe_err}")
            skipped_count += 1

    if not gallery_items:
        return PipelineReport(
            total_found=len(sources),
            processed_count=0,
            skipped_count=skipped_count,
            errors=errors,
            index_html_path=None,
        )

    try:
        index_path = build_gallery(gallery_items, config)
    except PermissionError as perm_exc:
        target = perm_exc.filename or str(config.output_dir / "index.html")
        errors.append(f"Error de permisos al compilar galería en '{target}': {perm_exc}")
        return PipelineReport(
            total_found=len(sources),
            processed_count=len(gallery_items),
            skipped_count=skipped_count,
            errors=errors,
            index_html_path=None,
        )

    return PipelineReport(
        total_found=len(sources),
        processed_count=len(gallery_items),
        skipped_count=skipped_count,
        errors=errors,
        index_html_path=index_path,
    )


class PixelForgeHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Manejador HTTP local que sirve output/ y procesa subidas seguras en POST /upload."""

    def __init__(
        self,
        *args: Any,
        directory: str | None = None,
        app_config: AppConfig | None = None,
        **kwargs: Any,
    ) -> None:
        self.app_config = app_config
        super().__init__(*args, directory=directory, **kwargs)

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/upload":
            self._send_json(404, {"ok": False, "error": "Ruta no encontrada."})
            return

        if self.app_config is None:
            self._send_json(500, {"ok": False, "error": "Configuración de pipeline no disponible."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        if content_length <= 0:
            self._send_json(400, {"ok": False, "error": "Archivo vacío o Content-Length inválido."})
            return

        if content_length > MAX_UPLOAD_BYTES:
            self._send_json(
                413,
                {"ok": False, "error": "La imagen supera el límite máximo permitido de 20 MB."},
            )
            return

        raw_header_name = self.headers.get("X-Filename", "upload.jpg")
        decoded_filename = urllib.parse.unquote(raw_header_name)
        file_bytes = self.rfile.read(content_length)

        try:
            with _PIPELINE_LOCK:
                saved_path = save_uploaded_image(
                    self.app_config.input_dir,
                    decoded_filename,
                    file_bytes,
                )
                report = run_pipeline(self.app_config)
        except ValueError as val_err:
            self._send_json(400, {"ok": False, "error": str(val_err)})
            return
        except Exception as exc:
            safe_msg = sanitize_secret_from_text(str(exc), self.app_config.gemini_api_key)
            self._send_json(500, {"ok": False, "error": f"Error interno al procesar: {safe_msg}"})
            return

        self._send_json(
            200,
            {
                "ok": True,
                "saved_filename": saved_path.name,
                "processed_count": report.processed_count,
            },
        )


def create_local_server(
    output_dir: Path,
    port: int = 8000,
    host: str = LOCALHOST_BIND,
    config: AppConfig | None = None,
) -> ThreadingHTTPServer:
    """Crea un servidor HTTP estático enlazado estrictamente a 127.0.0.1 (nunca 0.0.0.0)."""
    if host != LOCALHOST_BIND:
        raise ValueError(
            f"Violación de seguridad: el servidor local solo puede escuchar en "
            f"'{LOCALHOST_BIND}', nunca en '{host}'."
        )
    if port != 0 and not (1024 <= port <= 65535):
        raise ValueError(f"Puerto fuera de rango seguro (1024-65535): {port}")

    output_dir.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(
        PixelForgeHTTPRequestHandler,
        directory=str(output_dir.resolve()),
        app_config=config,
    )
    return ThreadingHTTPServer((LOCALHOST_BIND, port), handler)


def serve_gallery(
    output_dir: Path,
    port: int = 8000,
    host: str = LOCALHOST_BIND,
    config: AppConfig | None = None,
) -> None:
    """Inicia el servidor local de previsualización en http://127.0.0.1:<port>."""
    with create_local_server(output_dir=output_dir, port=port, host=host, config=config) as httpd:
        bound_port = httpd.server_address[1]
        print(f"Servidor PixelForge activo en http://{LOCALHOST_BIND}:{bound_port}")
        print("Puedes subir nuevas imágenes JPG/PNG directamente desde el navegador.")
        print("Presiona Ctrl+C para detener el servidor.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido por el usuario.")


def build_arg_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos CLI de PixelForge."""
    parser = argparse.ArgumentParser(
        prog="pixelforge",
        description="Pipeline local de procesamiento de imágenes por lotes con IA y galería web.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Ejecuta el pipeline sin conexión a Gemini API usando descripciones de respaldo.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Inicia un servidor web local en 127.0.0.1 al finalizar la compilación.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Puerto local para --serve (rango 1024-65535, por defecto: 8000).",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Directorio raíz del proyecto (por defecto: directorio actual).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal del CLI de PixelForge."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(base_dir=args.base_dir, offline=args.offline)
    except ValueError as cfg_err:
        print(f"[ERROR DE CONFIGURACIÓN] {cfg_err}", file=sys.stderr)
        return 2

    config.input_dir.mkdir(parents=True, exist_ok=True)
    report = run_pipeline(config)

    for err in report.errors:
        print(f"[AVISO] {err}", file=sys.stderr)

    if report.processed_count == 0 or report.index_html_path is None:
        if args.serve:
            empty_index = build_gallery([], config)
            print(f"Galería inicial preparada para subidas web en: {empty_index}")
            serve_gallery(config.output_dir, port=args.port, config=config)
            return 0

        print(
            f"Pipeline finalizado sin generar galería "
            f"(encontradas={report.total_found}, omitidas={report.skipped_count}).",
            file=sys.stderr,
        )
        return 1

    print(
        f"Pipeline completado con éxito: {report.processed_count}/{report.total_found} "
        f"imagen(es) procesada(s) (omitidas={report.skipped_count})."
    )
    print(f"Galería generada en: {report.index_html_path}")

    if args.serve:
        serve_gallery(config.output_dir, port=args.port, config=config)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
