import os
import shutil
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.utils import (
    BASE_DIR, ROOT_DIR, UPLOAD_DIR, PROCESSED_DIR,
    format_bytes, get_unique_filename, find_local_parent_pdfs, cleanup_old_files
)
from core.compressor import (
    start_compression_job, COMPRESSION_TASKS, COMPRESSION_PRESETS
)
from core.operations import (
    merge_pdfs, split_pdf, rotate_pdf, inspect_pdf, update_pdf_metadata
)
from core.web_to_pdf import convert_web_to_pdf, fetch_web_metadata
from core.ocr_scanner import start_ocr_job, OCR_TASKS

app = FastAPI(title="PDF Toolbox", description="Herramienta simple, limpia y potente para manipular PDFs")

# Montar estáticos y plantillas
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Página principal con interfaz limpia."""
    local_files = find_local_parent_pdfs()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "local_files": local_files,
            "presets": COMPRESSION_PRESETS
        }
    )


@app.get("/api/local-files")
async def list_local_files():
    """Retorna los PDFs detectados en la carpeta contenedora."""
    return {"files": find_local_parent_pdfs()}


def _resolve_input_file(
    uploaded_file: Optional[UploadFile],
    local_filename: Optional[str]
) -> Path:
    """Resuelve la ruta física del archivo (ya sea subido o seleccionado localmente)."""
    if local_filename:
        # Validar que no haya directory traversal
        clean_name = Path(local_filename).name
        target = ROOT_DIR / clean_name
        if target.is_file() and target.suffix.lower() == ".pdf":
            return target
        raise HTTPException(status_code=404, detail=f"Archivo local '{clean_name}' no encontrado en el directorio.")

    if uploaded_file and uploaded_file.filename:
        dest_filename = get_unique_filename(uploaded_file.filename, prefix="upload")
        dest_path = UPLOAD_DIR / dest_filename
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(uploaded_file.file, buffer)
        return dest_path

    raise HTTPException(status_code=400, detail="Debe proporcionar un archivo subido o seleccionar un archivo local.")


@app.post("/api/compress")
async def api_compress(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
    preset: str = Form("screen"),
    to_grayscale: bool = Form(False),
    custom_dpi: Optional[int] = Form(None)
):
    """Inicia la compresión asíncrona de un PDF."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        task_id = start_compression_job(
            input_path=str(input_path),
            preset=preset,
            to_grayscale=to_grayscale,
            custom_dpi=custom_dpi
        )
        background_tasks.add_task(cleanup_old_files)
        return {"success": True, "task_id": task_id, "message": "Proceso de compresión iniciado."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Consulta el estado del proceso de compresión."""
    task = COMPRESSION_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")
    return task


@app.post("/api/merge")
async def api_merge(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """Une múltiples archivos PDF subidos."""
    try:
        saved_paths = []
        for f in files:
            if not f.filename or not f.filename.lower().endswith(".pdf"):
                continue
            dest_name = get_unique_filename(f.filename, prefix="mpart")
            dest_path = UPLOAD_DIR / dest_name
            with open(dest_path, "wb") as buf:
                shutil.copyfileobj(f.file, buf)
            saved_paths.append(str(dest_path))

        if len(saved_paths) < 2:
            raise HTTPException(status_code=400, detail="Se requieren al menos 2 archivos PDF para unir.")

        result = merge_pdfs(saved_paths)
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/split")
async def api_split(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
    page_ranges: str = Form(...)
):
    """Extrae páginas de un PDF."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        result = split_pdf(str(input_path), page_ranges)
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rotate")
async def api_rotate(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
    angle: int = Form(90),
    page_ranges: Optional[str] = Form(None)
):
    """Rota páginas del PDF."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        result = rotate_pdf(str(input_path), angle, page_ranges)
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inspect")
async def api_inspect(
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None)
):
    """Inspecciona metadatos y páginas de un PDF."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        return inspect_pdf(str(input_path))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/web-metadata")
async def api_web_metadata(url: str = Form(...)):
    """Extrae rápidamente los metadatos de una URL para previsualizarlos y editarlos."""
    try:
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="La URL debe comenzar con http:// o https://")
        return fetch_web_metadata(clean_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/web-to-pdf")
async def api_web_to_pdf(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    mode: str = Form("reader"),
    style: str = Form("academic"),
    include_images: bool = Form(True),
    custom_title: Optional[str] = Form(None),
    custom_author: Optional[str] = Form(None),
    custom_date: Optional[str] = Form(None),
    zotero_mode: str = Form("standalone")
):
    """Convierte una página web o artículo a PDF con texto seleccionable para Zotero."""
    try:
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="La URL debe comenzar con http:// o https://")

        result = convert_web_to_pdf(
            url=clean_url,
            mode=mode,
            style=style,
            include_images=include_images,
            custom_title=custom_title,
            custom_author=custom_author,
            custom_date=custom_date,
            zotero_mode=zotero_mode
        )
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/update-metadata")
async def api_update_metadata(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    local_filename: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None)
):
    """Actualiza metadatos (autor, título, etc.) de cualquier PDF existente."""
    try:
        input_path = _resolve_input_file(file, local_filename)
        result = update_pdf_metadata(
            input_path=str(input_path),
            title=title,
            author=author,
            subject=subject,
            keywords=keywords
        )
        background_tasks.add_task(cleanup_old_files)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ocr-scan")
async def api_ocr_scan(
    background_tasks: BackgroundTasks,
    files: Optional[List[UploadFile]] = File(None),
    local_filename: Optional[str] = Form(None),
    language: str = Form("spa"),
    enhance_contrast: bool = Form(False),
    auto_orient: bool = Form(True),
    custom_title: Optional[str] = Form(None)
):
    """Inicia la digitalización y escaneo de páginas a PDF con OCR."""
    try:
        saved_paths: List[str] = []

        if local_filename:
            input_path = _resolve_input_file(None, local_filename)
            saved_paths.append(str(input_path))
        elif files:
            allowed_exts = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp"}
            for f in files:
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

        if not saved_paths:
            raise HTTPException(status_code=400, detail="Debe proporcionar al menos una imagen o un archivo PDF para digitalizar.")

        task_id = start_ocr_job(
            input_paths=saved_paths,
            language=language,
            enhance_contrast=enhance_contrast,
            auto_orient=auto_orient,
            custom_title=custom_title
        )
        background_tasks.add_task(cleanup_old_files)
        return {"success": True, "task_id": task_id, "message": "Proceso de digitalización OCR iniciado."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ocr-tasks/{task_id}")
async def get_ocr_task_status(task_id: str):
    """Consulta el estado del proceso de digitalización y OCR."""
    task = OCR_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarea de OCR no encontrada.")
    return task


@app.api_route("/api/download/{filename}", methods=["GET", "HEAD"])
async def download_file(filename: str):
    """Descarga un archivo procesado de manera segura (PDF o texto TXT)."""
    clean_name = Path(filename).name
    file_path = PROCESSED_DIR / clean_name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado o ha expirado.")

    media_type = "text/plain; charset=utf-8" if clean_name.lower().endswith(".txt") else "application/pdf"

    return FileResponse(
        path=str(file_path),
        filename=clean_name,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{clean_name}"'}
    )
