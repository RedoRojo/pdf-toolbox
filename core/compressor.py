"""
Asynchronous PDF compression engine using Ghostscript with PyMuPDF fallback.
"""

import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

import pymupdf

from .utils import format_bytes, get_unique_filename, cleanup_old_tasks, PROCESSED_DIR

# In-memory background task registry
COMPRESSION_TASKS: Dict[str, Dict[str, Any]] = {}

GS_BIN = shutil.which("gs") or "/usr/bin/gs"

COMPRESSION_PRESETS = {
    "screen": {
        "name": "Maximum Compression (Mobile / Web)",
        "description": "Resolution ~72 dpi. Smallest file size, ideal for sharing via chat or email.",
        "pdfsettings": "/screen",
        "dpi": 72,
    },
    "ebook": {
        "name": "Balanced (Recommended)",
        "description": "Resolution ~150 dpi. Great balance between crisp text and storage savings.",
        "pdfsettings": "/ebook",
        "dpi": 150,
    },
    "printer": {
        "name": "High Quality (Print)",
        "description": "Resolution ~300 dpi. Preserves high fidelity for graphics and images.",
        "pdfsettings": "/printer",
        "dpi": 300,
    },
}


def _find_gs_binary() -> Optional[str]:
    """Resolves the Ghostscript executable if available on the system."""
    candidate = shutil.which("gs") or (GS_BIN if Path(GS_BIN).is_file() else None)
    return candidate


def _run_compression_task(
    task_id: str,
    input_path: str,
    output_filename: str,
    preset: str = "ebook",
    to_grayscale: bool = False,
    custom_dpi: Optional[int] = None,
) -> None:
    task = COMPRESSION_TASKS.get(task_id)
    if not task:
        return

    t_start = time.time()
    temp_xref: Optional[Path] = None
    try:
        task["status"] = "processing"
        task["progress"] = 15
        task["message"] = "Starting PDF compression engine..."

        in_p = Path(input_path)
        if not in_p.is_file():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        orig_size = in_p.stat().st_size
        out_p = PROCESSED_DIR / output_filename

        gs_preset = COMPRESSION_PRESETS.get(preset, COMPRESSION_PRESETS["ebook"])
        pdfsettings = gs_preset["pdfsettings"]
        target_dpi = gs_preset["dpi"]
        if custom_dpi is not None:
            target_dpi = max(50, min(600, int(custom_dpi)))

        gs_bin = _find_gs_binary()
        gs_succeeded = False

        if gs_bin:
            cmd = [
                gs_bin,
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
                    "-dProcessColorModel=/DeviceGray",
                ])

            cmd.extend([
                f"-sOutputFile={str(out_p)}",
                str(in_p),
            ])

            task["progress"] = 35
            task["message"] = "Optimizing images, fonts, and document streams with Ghostscript..."

            try:
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=300,
                )
                gs_succeeded = (
                    process.returncode == 0
                    and out_p.exists()
                    and out_p.stat().st_size > 0
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                gs_succeeded = False

        if not gs_succeeded:
            task["progress"] = 55
            task["message"] = "Optimizing with fallback PyMuPDF engine..."
            doc = pymupdf.open(str(in_p))
            try:
                if doc.needs_pass:
                    raise ValueError("This PDF is password-protected and cannot be compressed.")
                doc.save(str(out_p), garbage=4, deflate=True, clean=True)
            finally:
                doc.close()

        task["progress"] = 85
        task["message"] = "Rebuilding XRef index and compacting..."

        # Final XRef optimization pass with PyMuPDF if it reduces file size further
        try:
            temp_xref = out_p.with_suffix(".xref.tmp")
            doc = pymupdf.open(str(out_p))
            try:
                doc.save(str(temp_xref), garbage=4, deflate=True, clean=True)
            finally:
                doc.close()
            if temp_xref.exists() and temp_xref.stat().st_size < out_p.stat().st_size:
                temp_xref.replace(out_p)
        except Exception:
            pass
        finally:
            if temp_xref and temp_xref.exists():
                temp_xref.unlink(missing_ok=True)

        final_size = out_p.stat().st_size
        saved_bytes = orig_size - final_size
        saved_pct = round((saved_bytes / orig_size) * 100, 1) if orig_size > 0 else 0.0
        duration = round(time.time() - t_start, 2)

        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = "Compression completed successfully!"
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
        task["message"] = f"Compression failed: {str(e)}"


def start_compression_job(
    input_path: str,
    preset: str = "ebook",
    to_grayscale: bool = False,
    custom_dpi: Optional[int] = None,
    output_filename: Optional[str] = None,
) -> str:
    """Starts a PDF compression job in a background thread and returns the task ID."""
    cleanup_old_tasks(COMPRESSION_TASKS)

    if preset not in COMPRESSION_PRESETS:
        preset = "ebook"

    task_id = uuid.uuid4().hex
    in_p = Path(input_path)
    if not output_filename:
        prefix = f"compressed_{preset}"
        if to_grayscale:
            prefix += "_gray"
        output_filename = get_unique_filename(in_p.name, prefix=prefix)

    COMPRESSION_TASKS[task_id] = {
        "id": task_id,
        "status": "pending",
        "progress": 5,
        "message": "Queued...",
        "created_at": time.time(),
        "result": None,
        "error": None,
    }

    thread = threading.Thread(
        target=_run_compression_task,
        args=(task_id, input_path, output_filename, preset, to_grayscale, custom_dpi),
        daemon=True,
    )
    thread.start()
    return task_id
