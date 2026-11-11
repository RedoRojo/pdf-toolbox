"""
OCR scanning and digitization module using Tesseract OCR and PyMuPDF.
Converts page photographs or scanned PDFs into searchable PDFs with selectable text layers.
"""

import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageOps
import pymupdf

from .utils import format_bytes, get_unique_filename, cleanup_old_tasks, BASE_DIR, UPLOAD_DIR, PROCESSED_DIR

OCR_TASKS: Dict[str, Dict[str, Any]] = {}

LOCAL_TESSDATA = BASE_DIR / "tessdata"


def _find_tesseract_binary() -> str:
    """Finds the Tesseract OCR executable across common cross-platform locations."""
    candidates = [
        shutil.which("tesseract"),
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(
        "Tesseract OCR executable not found. Please install 'tesseract-ocr' and language packs on your system."
    )


def _candidate_tessdata_dirs() -> List[Path]:
    """Returns candidate tessdata directories in lookup priority order."""
    dirs: List[Path] = [LOCAL_TESSDATA]
    env_dir = os.environ.get("TESSDATA_PREFIX")
    if env_dir:
        dirs.append(Path(env_dir))
    dirs.extend([
        Path("/usr/share/tessdata"),
        Path("/usr/share/tesseract-ocr/5/tessdata"),
        Path("/usr/share/tesseract-ocr/4.00/tessdata"),
        Path("/usr/local/share/tessdata"),
        Path("/opt/homebrew/share/tessdata"),
    ])

    seen = set()
    unique: List[Path] = []
    for d in dirs:
        try:
            resolved = d.resolve()
        except OSError:
            resolved = d
        if resolved not in seen and d.is_dir():
            seen.add(resolved)
            unique.append(d)
    return unique


def prepare_tessdata_dir(work_dir: Path, lang_code: str, auto_orient: bool) -> Tuple[str, bool]:
    """
    Resolves or assembles a valid tessdata directory containing all requested language packs.
    Handles systems where bundled languages (e.g., spa) live in ./tessdata while system languages
    (e.g., eng, osd) live in /usr/share/tessdata or /usr/share/tesseract-ocr/*/tessdata.
    Returns (tessdata_dir_path, has_osd).
    """
    required_langs = [part.strip() for part in lang_code.split("+") if part.strip()]
    if not required_langs:
        required_langs = ["eng"]

    candidates = _candidate_tessdata_dirs()

    # Check if any single directory satisfies all requested files cleanly
    for candidate in candidates:
        all_langs_present = all((candidate / f"{lang}.traineddata").exists() for lang in required_langs)
        osd_present = (candidate / "osd.traineddata").exists()
        if all_langs_present and (not auto_orient or osd_present):
            return str(candidate), osd_present

    # Otherwise, assemble a runtime staging directory inside work_dir combining available assets
    staged = work_dir / "tessdata"
    staged.mkdir(parents=True, exist_ok=True)

    # Copy/link configs, tessconfigs, and pdf.ttf from candidate dirs if needed
    for helper_name in ("configs", "tessconfigs", "pdf.ttf"):
        dest = staged / helper_name
        if dest.exists():
            continue
        for candidate in candidates:
            src = candidate / helper_name
            if src.exists():
                if src.is_dir():
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dest)
                break

    for lang in required_langs:
        found_path: Optional[Path] = None
        for candidate in candidates:
            p = candidate / f"{lang}.traineddata"
            if p.exists():
                found_path = p.resolve()
                break
        if not found_path:
            raise FileNotFoundError(
                f"Tesseract language data '{lang}.traineddata' was not found. "
                f"Install the '{lang}' language pack or place it in tessdata/."
            )
        target = staged / f"{lang}.traineddata"
        try:
            target.symlink_to(found_path)
        except OSError:
            shutil.copy2(found_path, target)

    has_osd = False
    for candidate in candidates:
        osd_src = candidate / "osd.traineddata"
        if osd_src.exists():
            osd_target = staged / "osd.traineddata"
            try:
                osd_target.symlink_to(osd_src.resolve())
            except OSError:
                shutil.copy2(osd_src.resolve(), osd_target)
            has_osd = True
            break

    return str(staged), has_osd


def natural_sort_key(s: str) -> List[Any]:
    """Natural sort key (e.g., page1, page2, page10 instead of page1, page10, page2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", str(s))]


def preprocess_image(input_img_path: Path, output_img_path: Path, enhance_contrast: bool = False) -> Path:
    """Preprocesses a page image to optimize OCR readability."""
    try:
        with Image.open(input_img_path) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            if enhance_contrast:
                img = ImageOps.autocontrast(img, cutoff=1)
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.3)

            img.save(output_img_path, format="PNG", optimize=True)
            return output_img_path
    except Exception:
        return input_img_path


def _run_ocr_task(
    task_id: str,
    input_paths: List[str],
    output_pdf_name: str,
    output_txt_name: str,
    language: str = "eng",
    enhance_contrast: bool = False,
    auto_orient: bool = True,
    custom_title: Optional[str] = None,
) -> None:
    task = OCR_TASKS.get(task_id)
    if not task:
        return

    t_start = time.time()
    work_dir = UPLOAD_DIR / f"ocr_tmp_{task_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        task["status"] = "processing"
        task["progress"] = 5
        task["message"] = "Analyzing input files..."

        tesseract_bin = _find_tesseract_binary()

        lang_code = language.strip() or "eng"
        if not re.fullmatch(r"[a-zA-Z0-9_]+(\+[a-zA-Z0-9_]+)*", lang_code):
            raise ValueError(f"Invalid OCR language code: '{lang_code}'")

        tessdata_dir, has_osd = prepare_tessdata_dir(work_dir, lang_code, auto_orient=auto_orient)
        images_to_process: List[Path] = []

        if len(input_paths) == 1 and input_paths[0].lower().endswith(".pdf"):
            pdf_path = Path(input_paths[0])
            task["message"] = "Extracting PDF pages for digitization..."
            doc = pymupdf.open(str(pdf_path))
            try:
                if doc.needs_pass:
                    raise ValueError("This PDF is password-protected and cannot be scanned.")
                total_doc_pages = len(doc)
                for pno in range(total_doc_pages):
                    page = doc[pno]
                    pix = page.get_pixmap(dpi=250)
                    img_path = work_dir / f"extracted_page_{pno + 1:04d}.png"
                    pix.save(str(img_path))
                    images_to_process.append(img_path)
            finally:
                doc.close()
        else:
            sorted_paths = sorted(input_paths, key=natural_sort_key)
            images_to_process = [Path(p) for p in sorted_paths if Path(p).is_file()]

        total_pages = len(images_to_process)
        if total_pages == 0:
            raise ValueError("No valid pages found to process.")

        task["total_pages"] = total_pages
        task["message"] = f"Starting OCR for {total_pages} page(s)..."
        task["progress"] = 10

        page_pdf_files: List[Path] = []
        all_text_lines: List[str] = []

        for idx, img_path in enumerate(images_to_process):
            page_num = idx + 1
            task["current_page"] = page_num
            task["progress"] = int(10 + (idx / total_pages) * 75)
            task["message"] = f"Running OCR on page {page_num} of {total_pages} ({lang_code})..."

            proc_img = work_dir / f"proc_{img_path.name}"
            final_img = preprocess_image(img_path, proc_img, enhance_contrast=enhance_contrast)
            page_output_base = work_dir / f"ocr_page_{page_num:04d}"

            use_osd = auto_orient and has_osd
            psm_mode = "1" if use_osd else "3"

            cmd = [
                tesseract_bin,
                "--tessdata-dir",
                tessdata_dir,
                "-l",
                lang_code,
                "--psm",
                psm_mode,
                str(final_img),
                str(page_output_base),
                "pdf",
                "txt",
            ]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 and psm_mode == "1":
                retry_cmd = [
                    tesseract_bin,
                    "--tessdata-dir",
                    tessdata_dir,
                    "-l",
                    lang_code,
                    "--psm",
                    "3",
                    str(final_img),
                    str(page_output_base),
                    "pdf",
                    "txt",
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
                        all_text_lines.append(f"--- [Page {page_num}] ---\n{txt_content}\n")
                except OSError:
                    pass

        if not page_pdf_files:
            raise RuntimeError(
                "The OCR engine failed to generate valid pages. Verify image quality and installed languages."
            )

        task["progress"] = 88
        task["message"] = "Assembling final searchable PDF document..."

        out_pdf_path = PROCESSED_DIR / output_pdf_name
        final_doc = pymupdf.open()
        try:
            for p_pdf in page_pdf_files:
                temp_page_doc = pymupdf.open(str(p_pdf))
                try:
                    final_doc.insert_pdf(temp_page_doc)
                finally:
                    temp_page_doc.close()

            title_meta = custom_title.strip() if custom_title else "Digitized OCR Document"
            final_doc.set_metadata({
                "title": title_meta,
                "creator": "PDF Toolbox — OCR Scanner",
                "producer": "Tesseract OCR + PyMuPDF",
            })
            final_doc.save(str(out_pdf_path), garbage=4, deflate=True)
        finally:
            final_doc.close()

        out_txt_path = PROCESSED_DIR / output_txt_name
        full_text = "\n".join(all_text_lines)
        out_txt_path.write_text(full_text, encoding="utf-8")

        sample_chars = full_text[:1200]
        if len(full_text) > 1200:
            sample_chars += "\n\n[... full text available in download ...]"

        duration = round(time.time() - t_start, 2)
        final_pdf_size = out_pdf_path.stat().st_size
        final_txt_size = out_txt_path.stat().st_size

        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = f"Digitization completed! {total_pages} page(s) processed successfully."
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
            "text_sample": sample_chars or "(No text detected in the document)",
        }

    except Exception as e:
        task["status"] = "failed"
        task["progress"] = 100
        task["error"] = str(e)
        task["message"] = f"OCR digitization error: {str(e)}"
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def start_ocr_job(
    input_paths: List[str],
    language: str = "eng",
    enhance_contrast: bool = False,
    auto_orient: bool = True,
    custom_title: Optional[str] = None,
) -> str:
    """Starts a background OCR scan job and returns its task ID."""
    cleanup_old_tasks(OCR_TASKS)

    task_id = uuid.uuid4().hex
    prefix = "ocr_scan"
    base_name = custom_title.strip() if custom_title else "document"
    output_pdf_name = get_unique_filename(f"{base_name}.pdf", prefix=prefix)
    output_txt_name = get_unique_filename(f"{base_name}.txt", prefix=prefix)

    OCR_TASKS[task_id] = {
        "id": task_id,
        "status": "pending",
        "progress": 3,
        "message": "Preparing pages for scanning...",
        "created_at": time.time(),
        "total_pages": len(input_paths),
        "current_page": 0,
        "result": None,
        "error": None,
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
            custom_title,
        ),
        daemon=True,
    )
    thread.start()
    return task_id
