"""
PDF Toolbox - FastAPI Web Server
Local toolkit for OCR digitization, PDF compression, page operations,
metadata editing, and web article to PDF conversion.
"""

import shutil
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.utils import (
    BASE_DIR,
    ROOT_DIR,
    UPLOAD_DIR,
    PROCESSED_DIR,
    get_unique_filename,
    find_local_parent_pdfs,
    cleanup_old_files,
)
from core.compressor import (
    start_compression_job,
    COMPRESSION_TASKS,
    COMPRESSION_PRESETS,
)
from core.operations import (
    merge_pdfs,
    split_pdf,
    rotate_pdf,
    inspect_pdf,
    update_pdf_metadata,
)
from core.web_to_pdf import convert_web_to_pdf, fetch_web_metadata
from core.ocr_scanner import start_ocr_job, OCR_TASKS

app = FastAPI(
    title="PDF Toolbox",
    description="Fast, clean, and lightweight local web toolkit for PDF optimization, OCR, manipulation, and web article conversion.",
)

# Mount static assets and Jinja2 templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    """Main web application UI."""
    local_files = find_local_parent_pdfs()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "local_files": local_files,
            "presets": COMPRESSION_PRESETS,
        },
    )


@app.get("/api/local-files")
def list_local_files():
    """Returns PDF files detected in the parent workspace directory."""
    return {"files": find_local_parent_pdfs()}


def _resolve_input_file(
    uploaded_file: Optional[UploadFile],
    local_filename: Optional[str],
) -> Path:
    """Resolves the physical path of an uploaded or locally selected PDF file."""
    if local_filename:
        clean_name = Path(local_filename).name
        target = ROOT_DIR / clean_name
        if target.is_file() and target.suffix.lower() == ".pdf":
            return target
        raise HTTPException(
            status_code=404,
            detail=f"Local file '{clean_name}' was not found in the parent directory.",
        )

    if uploaded_file and uploaded_file.filename:
        if Path(uploaded_file.filename).suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="Only .pdf files are supported.")
        dest_filename = get_unique_filename(uploaded_file.filename, prefix="upload")
        dest_path = UPLOAD_DIR / dest_filename
        try:
            with open(dest_path, "wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)
        finally:
            uploaded_file.file.close()
        return dest_path

    raise HTTPException(
        status_code=400,
        detail="You must upload a PDF file or select a local file.",
    )


@app.post("/api/compress")
def api_compress(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
    preset: str = Form("screen"),
    to_grayscale: bool = Form(False),
    custom_dpi: Optional[int] = Form(None),
):
    """Starts an asynchronous PDF compression job."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        task_id = start_compression_job(
            input_path=str(input_path),
            preset=preset,
            to_grayscale=to_grayscale,
            custom_dpi=custom_dpi,
        )
        background_tasks.add_task(cleanup_old_files)
        return {"success": True, "task_id": task_id, "message": "Compression job started."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str):
    """Returns the status of a background compression job."""
    task = COMPRESSION_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Compression task not found.")
    return task


@app.post("/api/merge")
def api_merge(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    """Merges multiple uploaded PDF files into one document."""
    try:
        saved_paths: List[str] = []
        for f in files:
            try:
                if not f.filename or not f.filename.lower().endswith(".pdf"):
                    continue
                dest_name = get_unique_filename(f.filename, prefix="mpart")
                dest_path = UPLOAD_DIR / dest_name
                with open(dest_path, "wb") as buf:
                    shutil.copyfileobj(f.file, buf)
                saved_paths.append(str(dest_path))
            finally:
                f.file.close()

        if len(saved_paths) < 2:
            raise HTTPException(status_code=400, detail="At least 2 PDF files are required to merge.")

        result = merge_pdfs(saved_paths)
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/split")
def api_split(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
    page_ranges: str = Form(...),
):
    """Extracts selected pages from a PDF."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        result = split_pdf(str(input_path), page_ranges)
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rotate")
def api_rotate(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
    angle: int = Form(90),
    page_ranges: Optional[str] = Form(None),
):
    """Rotates all or selected PDF pages by 90, 180, or 270 degrees."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        result = rotate_pdf(str(input_path), angle, page_ranges)
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inspect")
def api_inspect(
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
):
    """Inspects metadata, page count, and structure of a PDF."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        return inspect_pdf(str(input_path))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/web-metadata")
def api_web_metadata(url: str = Form(...)):
    """Fetches article metadata from a URL for live preview and editing."""
    try:
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
        return fetch_web_metadata(clean_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/web-to-pdf")
def api_web_to_pdf(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    mode: str = Form("reader"),
    style: str = Form("academic"),
    include_images: bool = Form(True),
    custom_title: Optional[str] = Form(None),
    custom_author: Optional[str] = Form(None),
    custom_date: Optional[str] = Form(None),
    zotero_mode: str = Form("standalone"),
):
    """Converts a webpage or article into a selectable vector PDF tailored for Zotero."""
    try:
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

        safe_mode = mode if mode in ("reader", "fullpage") else "reader"
        safe_style = style if style in ("academic", "sans") else "academic"
        safe_zotero = zotero_mode if zotero_mode in ("standalone", "parent") else "standalone"

        result = convert_web_to_pdf(
            url=clean_url,
            mode=safe_mode,
            style=safe_style,
            include_images=include_images,
            custom_title=custom_title,
            custom_author=custom_author,
            custom_date=custom_date,
            zotero_mode=safe_zotero,
        )
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/update-metadata")
def api_update_metadata(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
):
    """Updates PDF metadata fields (title, author, subject, keywords)."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        result = update_pdf_metadata(
            input_path=str(input_path),
            title=title,
            author=author,
            subject=subject,
            keywords=keywords,
        )
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ocr-scan")
def api_ocr_scan(
    background_tasks: BackgroundTasks,
    files: Optional[List[UploadFile]] = File(None),
    local_filename: Optional[str] = Form(None),
    language: str = Form("eng"),
    enhance_contrast: bool = Form(False),
    auto_orient: bool = Form(True),
    custom_title: Optional[str] = Form(None),
):
    """Starts an asynchronous OCR digitization job for images or scanned PDFs."""
    try:
        saved_paths: List[str] = []

        if local_filename:
            input_path = _resolve_input_file(None, local_filename)
            saved_paths.append(str(input_path))
        elif files:
            allowed_exts = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp"}
            for f in files:
                try:
                    if not f.filename:
                        continue
                    ext = Path(f.filename).suffix.lower()
                    if ext not in allowed_exts:
                        continue
                    dest_name = get_unique_filename(f.filename, prefix="ocr_in")
                    dest_path = UPLOAD_DIR / dest_name
                    with open(dest_path, "wb") as buf:
                        shutil.copyfileobj(f.file, buf)
                    saved_paths.append(str(dest_path))
                finally:
                    f.file.close()

        if not saved_paths:
            raise HTTPException(
                status_code=400,
                detail="You must provide at least one image or PDF file to digitize.",
            )

        task_id = start_ocr_job(
            input_paths=saved_paths,
            language=language,
            enhance_contrast=enhance_contrast,
            auto_orient=auto_orient,
            custom_title=custom_title,
        )
        background_tasks.add_task(cleanup_old_files)
        return {"success": True, "task_id": task_id, "message": "OCR digitization job started."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ocr-tasks/{task_id}")
def get_ocr_task_status(task_id: str):
    """Returns the status of an OCR digitization task."""
    task = OCR_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="OCR task not found.")
    return task


@app.api_route("/api/download/{filename}", methods=["GET", "HEAD"])
def download_file(filename: str):
    """Safely serves a processed PDF or text transcription file for download."""
    clean_name = Path(filename).name
    file_path = PROCESSED_DIR / clean_name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found or has expired.")

    media_type = "text/plain; charset=utf-8" if clean_name.lower().endswith(".txt") else "application/pdf"

    return FileResponse(
        path=str(file_path),
        filename=clean_name,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{clean_name}"'},
    )
