import os
import subprocess
import shutil
import time
import threading
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
import pymupdf

from .utils import format_bytes, get_unique_filename, PROCESSED_DIR

# Registro de tareas en memoria
COMPRESSION_TASKS: Dict[str, Dict[str, Any]] = {}

GS_BIN = shutil.which("gs") or "/usr/bin/gs"

COMPRESSION_PRESETS = {
    "screen": {
        "name": "Máxima compresión (Móvil/Web)",
        "description": "Resolución ~72 dpi. Mayor reducción de tamaño, ideal para compartir por chat o correo.",
        "pdfsettings": "/screen",
        "dpi": 72
    },
    "ebook": {
        "name": "Recomendada (Equilibrada)",
        "description": "Resolución ~150 dpi. Excelente balance entre nitidez de texto y ahorro de espacio.",
        "pdfsettings": "/ebook",
        "dpi": 150
    },
    "printer": {
        "name": "Alta calidad (Impresión)",
        "description": "Resolución ~300 dpi. Mantiene alta fidelidad de gráficos e imágenes.",
        "pdfsettings": "/printer",
        "dpi": 300
    }
}


def _run_compression_task(
    task_id: str,
    input_path: str,
    output_filename: str,
    preset: str = "ebook",
    to_grayscale: bool = False,
    custom_dpi: Optional[int] = None
):
    task = COMPRESSION_TASKS.get(task_id)
    if not task:
        return

    t_start = time.time()
    try:
        task["status"] = "processing"
        task["progress"] = 15
        task["message"] = "Iniciando motor de compresión Ghostscript..."

        in_p = Path(input_path)
        if not in_p.is_file():
            raise FileNotFoundError(f"Archivo de entrada no existe: {input_path}")

        orig_size = in_p.stat().st_size
        out_p = PROCESSED_DIR / output_filename

        # Armar comando Ghostscript
        gs_preset = COMPRESSION_PRESETS.get(preset, COMPRESSION_PRESETS["ebook"])
        pdfsettings = gs_preset["pdfsettings"]
        target_dpi = custom_dpi or gs_preset["dpi"]

        cmd = [
            GS_BIN,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={pdfsettings}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            "-dDownsampleColorImages=true",
            f"-dColorImageResolution={target_dpi}",
            "-dColorImageDownsampleType=/Bicubic",
            "-dDownsampleGrayImages=true",
            f"-dGrayImageResolution={target_dpi}",
            "-dDownsampleMonoImages=true",
            "-dMonoImageResolution=150",
        ]

        if to_grayscale:
            cmd.extend([
                "-sColorConversionStrategy=Gray",
                "-dProcessColorModel=/DeviceGray"
            ])

        cmd.extend([
            f"-sOutputFile={str(out_p)}",
            str(in_p)
        ])

        task["progress"] = 35
        task["message"] = "Optimizando imágenes, fuentes y streams del documento..."

        # Ejecutar Ghostscript
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if process.returncode != 0 or not out_p.exists() or out_p.stat().st_size == 0:
            # Fallback con PyMuPDF
            task["message"] = "Optimizando con motor secundario PyMuPDF..."
            doc = pymupdf.open(str(in_p))
            doc.save(str(out_p), garbage=4, deflate=True, clean=True)
            doc.close()

        task["progress"] = 85
        task["message"] = "Reconstruyendo índice XRef y compactando..."

        # Intentar optimización final de XRef con PyMuPDF si no incrementa el peso
        try:
            temp_xref = out_p.with_suffix(".xref.tmp")
            doc = pymupdf.open(str(out_p))
            doc.save(str(temp_xref), garbage=4, deflate=True, clean=True)
            doc.close()
            if temp_xref.exists() and temp_xref.stat().st_size < out_p.stat().st_size:
                temp_xref.replace(out_p)
            elif temp_xref.exists():
                temp_xref.unlink(missing_ok=True)
        except Exception:
            pass

        final_size = out_p.stat().st_size
        saved_bytes = orig_size - final_size
        saved_pct = round((saved_bytes / orig_size) * 100, 1) if orig_size > 0 else 0
        duration = round(time.time() - t_start, 2)

        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = "¡Compresión completada con éxito!"
        task["result"] = {
            "filename": output_filename,
            "filepath": str(out_p),
            "original_size_bytes": orig_size,
            "original_size_formatted": format_bytes(orig_size),
            "compressed_size_bytes": final_size,
            "compressed_size_formatted": format_bytes(final_size),
            "saved_bytes": saved_bytes,
            "saved_bytes_formatted": format_bytes(max(0, saved_bytes)),
            "saved_percentage": saved_pct,
            "duration_seconds": duration,
            "preset": preset,
            "to_grayscale": to_grayscale,
        }
    except Exception as e:
        task["status"] = "failed"
        task["progress"] = 100
        task["error"] = str(e)
        task["message"] = f"Error durante la compresión: {str(e)}"


def start_compression_job(
    input_path: str,
    preset: str = "ebook",
    to_grayscale: bool = False,
    custom_dpi: Optional[int] = None,
    output_filename: Optional[str] = None
) -> str:
    """Inicia una tarea de compresión en un hilo separado y retorna el taskId."""
    task_id = uuid.uuid4().hex
    in_p = Path(input_path)
    if not output_filename:
        prefix = f"aligerado_{preset}"
        if to_grayscale:
            prefix += "_gris"
        output_filename = get_unique_filename(in_p.name, prefix=prefix)

    COMPRESSION_TASKS[task_id] = {
        "id": task_id,
        "status": "pending",
        "progress": 5,
        "message": "En cola...",
        "created_at": time.time(),
        "result": None,
        "error": None
    }

    thread = threading.Thread(
        target=_run_compression_task,
        args=(task_id, input_path, output_filename, preset, to_grayscale, custom_dpi),
        daemon=True
    )
    thread.start()
    return task_id
