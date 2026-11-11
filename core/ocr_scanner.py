import os
import re
import shutil
import subprocess
import time
import threading
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from PIL import Image, ImageEnhance, ImageOps
import pymupdf

from .utils import format_bytes, get_unique_filename, BASE_DIR, PROCESSED_DIR, UPLOAD_DIR

OCR_TASKS: Dict[str, Dict[str, Any]] = {}

TESSERACT_BIN = shutil.which("tesseract") or "/usr/bin/tesseract"
LOCAL_TESSDATA = BASE_DIR / "tessdata"
SYS_TESSDATA = Path("/usr/share/tessdata")


def get_tessdata_path() -> str:
    """Retorna la ruta al directorio tessdata preferido (local o del sistema)."""
    if LOCAL_TESSDATA.is_dir() and (LOCAL_TESSDATA / "spa.traineddata").exists():
        return str(LOCAL_TESSDATA)
    if SYS_TESSDATA.is_dir():
        return str(SYS_TESSDATA)
    return str(LOCAL_TESSDATA)


def natural_sort_key(s: str):
    """Clave para ordenamiento natural (ej. pag1, pag2, pag10 en lugar de pag1, pag10, pag2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", str(s))]


def preprocess_image(input_img_path: Path, output_img_path: Path, enhance_contrast: bool = False) -> Path:
    """Preprocesa una imagen para optimizar la legibilidad del OCR."""
    try:
        with Image.open(input_img_path) as img:
            # Convertir a RGB si tiene canal alpha o CMYK
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            if enhance_contrast:
                # Normalizar contraste y aumentar ligeramente nitidez de bordes
                img = ImageOps.autocontrast(img, cutoff=1)
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.3)

            img.save(output_img_path, format="PNG", optimize=True)
            return output_img_path
    except Exception:
        # En caso de error, usar la imagen original
        return input_img_path


def _run_ocr_task(
    task_id: str,
    input_paths: List[str],
    output_pdf_name: str,
    output_txt_name: str,
    language: str = "spa",
    enhance_contrast: bool = False,
    auto_orient: bool = True,
    custom_title: Optional[str] = None
):
    task = OCR_TASKS.get(task_id)
    if not task:
        return

    t_start = time.time()
    work_dir = BASE_DIR / "uploads" / f"ocr_tmp_{task_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        task["status"] = "processing"
        task["progress"] = 5
        task["message"] = "Analizando archivos de entrada..."

        tessdata_dir = get_tessdata_path()
        images_to_process: List[Path] = []

        # Verificar si la entrada es un único PDF o una lista de imágenes
        if len(input_paths) == 1 and input_paths[0].lower().endswith(".pdf"):
            pdf_path = Path(input_paths[0])
            task["message"] = "Extrayendo páginas del PDF para digitalización..."
            doc = pymupdf.open(str(pdf_path))
            total_doc_pages = len(doc)

            for pno in range(total_doc_pages):
                page = doc[pno]
                # Renderizar página a 250 DPI (excelente balance entre nitidez y velocidad para OCR)
                pix = page.get_pixmap(dpi=250)
                img_path = work_dir / f"extracted_page_{pno+1:04d}.png"
                pix.save(str(img_path))
                images_to_process.append(img_path)
            doc.close()
        else:
            # Es un lote de imágenes; ordenarlas naturalmente
            sorted_paths = sorted(input_paths, key=natural_sort_key)
            images_to_process = [Path(p) for p in sorted_paths if Path(p).is_file()]

        total_pages = len(images_to_process)
        if total_pages == 0:
            raise ValueError("No se encontraron páginas válidas para procesar.")

        task["total_pages"] = total_pages
        task["message"] = f"Iniciando OCR para {total_pages} página(s)..."
        task["progress"] = 10

        page_pdf_files: List[Path] = []
        all_text_lines: List[str] = []

        # Validar idioma seleccionado
        lang_code = language.strip()
        if not lang_code:
            lang_code = "spa"

        # Procesar página por página para actualizar el progreso
        for idx, img_path in enumerate(images_to_process):
            page_num = idx + 1
            task["current_page"] = page_num
            task["progress"] = int(10 + (idx / total_pages) * 75)
            task["message"] = f"Procesando página {page_num} de {total_pages} con OCR ({lang_code})..."

            # Preprocesamiento si es solicitado
            proc_img = work_dir / f"proc_{img_path.name}"
            final_img = preprocess_image(img_path, proc_img, enhance_contrast=enhance_contrast)

            # Base de salida para esta página
            page_output_base = work_dir / f"ocr_page_{page_num:04d}"

            # Construir comando Tesseract
            cmd = [
                TESSERACT_BIN,
                "--tessdata-dir", tessdata_dir,
                "-l", lang_code,
            ]

            if auto_orient:
                cmd.extend(["--psm", "1"])  # Auto con OSD (Orientation and Script Detection)
            else:
                cmd.extend(["--psm", "3"])  # Auto segmentación estándar

            cmd.extend([
                str(final_img),
                str(page_output_base),
                "pdf", "txt"
            ])

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                # Si falló con PSM 1 (por ejemplo, imagen muy pequeña), reintentar con PSM 3 por defecto
                retry_cmd = [
                    TESSERACT_BIN,
                    "--tessdata-dir", tessdata_dir,
                    "-l", lang_code,
                    "--psm", "3",
                    str(final_img),
                    str(page_output_base),
                    "pdf", "txt"
                ]
                subprocess.run(retry_cmd, capture_output=True, text=True)

            page_pdf = work_dir / f"ocr_page_{page_num:04d}.pdf"
            page_txt = work_dir / f"ocr_page_{page_num:04d}.txt"

            if page_pdf.exists():
                page_pdf_files.append(page_pdf)

            if page_txt.exists():
                try:
                    txt_content = page_txt.read_text(encoding="utf-8", errors="replace").strip()
                    if txt_content:
                        all_text_lines.append(f"--- [Página {page_num}] ---\n" + txt_content + "\n")
                except Exception:
                    pass

        if not page_pdf_files:
            raise RuntimeError("El motor OCR no generó páginas válidas. Verifique la calidad de las imágenes.")

        task["progress"] = 88
        task["message"] = "Ensamblando documento PDF final con capa de texto..."

        # Unir todas las páginas generadas en un único PDF
        final_doc = pymupdf.open()
        for p_pdf in page_pdf_files:
            temp_page_doc = pymupdf.open(str(p_pdf))
            final_doc.insert_pdf(temp_page_doc)
            temp_page_doc.close()

        # Establecer metadatos
        title_meta = custom_title.strip() if custom_title else "Documento Digitalizado OCR"
        final_doc.set_metadata({
            "title": title_meta,
            "creator": "PDF Toolbox — Escáner OCR",
            "producer": "Tesseract OCR + PyMuPDF",
        })

        out_pdf_path = PROCESSED_DIR / output_pdf_name
        final_doc.save(str(out_pdf_path), garbage=4, deflate=True)
        final_doc.close()

        # Guardar transcripción en archivo TXT
        out_txt_path = PROCESSED_DIR / output_txt_name
        full_text = "\n".join(all_text_lines)
        out_txt_path.write_text(full_text, encoding="utf-8")

        # Muestra de texto para la vista previa
        sample_chars = full_text[:1200]
        if len(full_text) > 1200:
            sample_chars += "\n\n[... texto completo disponible en la descarga ...]"

        duration = round(time.time() - t_start, 2)
        final_pdf_size = out_pdf_path.stat().st_size
        final_txt_size = out_txt_path.stat().st_size

        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = f"¡Digitalización completada! {total_pages} página(s) procesadas con éxito."
        task["result"] = {
            "filename": output_pdf_name,
            "filepath": str(out_pdf_path),
            "text_filename": output_txt_name,
            "total_pages": total_pages,
            "language": lang_code,
            "pdf_size_bytes": final_pdf_size,
            "pdf_size_formatted": format_bytes(final_pdf_size),
            "txt_size_bytes": final_txt_size,
            "txt_size_formatted": format_bytes(final_txt_size),
            "duration_seconds": duration,
            "text_sample": sample_chars or "(No se detectó texto en el documento)",
        }

    except Exception as e:
        task["status"] = "failed"
        task["progress"] = 100
        task["error"] = str(e)
        task["message"] = f"Error durante la digitalización OCR: {str(e)}"
    finally:
        # Limpieza del directorio de trabajo temporal de esta tarea
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


def start_ocr_job(
    input_paths: List[str],
    language: str = "spa",
    enhance_contrast: bool = False,
    auto_orient: bool = True,
    custom_title: Optional[str] = None
) -> str:
    """Inicia una tarea de escaneo y OCR en segundo plano y retorna el taskId."""
    task_id = uuid.uuid4().hex
    prefix = "escaneo_ocr"
    base_name = custom_title.strip() if custom_title else "documento"
    output_pdf_name = get_unique_filename(f"{base_name}.pdf", prefix=prefix)
    output_txt_name = get_unique_filename(f"{base_name}.txt", prefix=prefix)

    OCR_TASKS[task_id] = {
        "id": task_id,
        "status": "pending",
        "progress": 3,
        "message": "Preparando páginas para escaneo...",
        "created_at": time.time(),
        "total_pages": len(input_paths),
        "current_page": 0,
        "result": None,
        "error": None
    }

    thread = threading.Thread(
        target=_run_ocr_task,
        args=(
            task_id,
            input_paths,
            output_pdf_name,
            output_txt_name,
            language,
            enhance_contrast,
            auto_orient,
            custom_title
        ),
        daemon=True
    )
    thread.start()
    return task_id
