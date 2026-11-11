import os
import uuid
import shutil
import time
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
UPLOAD_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = BASE_DIR / "processed"

# Asegurar directorios
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def format_bytes(size_bytes: int) -> str:
    """Convierte bytes a formato legible (KB, MB, GB)."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"


def get_unique_filename(original_name: str, prefix: str = "") -> str:
    """Genera un nombre de archivo seguro preservando la extensión original."""
    ext = Path(original_name).suffix or ".pdf"
    clean_stem = "".join(c for c in Path(original_name).stem if c.isalnum() or c in ("-", "_"))[:35]
    if not clean_stem:
        clean_stem = "documento"
    token = uuid.uuid4().hex[:8]
    if prefix:
        return f"{prefix}_{clean_stem}_{token}{ext}"
    return f"{clean_stem}_{token}{ext}"


def find_local_parent_pdfs() -> List[Dict[str, Any]]:
    """Encuentra archivos PDF disponibles en el directorio superior de la herramienta."""
    files = []
    try:
        for p in ROOT_DIR.glob("*.pdf"):
            if p.is_file():
                stat = p.stat()
                files.append({
                    "filename": p.name,
                    "filepath": str(p.resolve()),
                    "size_bytes": stat.st_size,
                    "size_formatted": format_bytes(stat.st_size),
                    "is_test_file": p.name == "tomo25.pdf"
                })
    except Exception as e:
        pass
    # Ordenar poniendo archivos de prueba o más recientes primero
    files.sort(key=lambda x: (not x["is_test_file"], -x["size_bytes"]))
    return files


def cleanup_old_files(max_age_hours: int = 6):
    """Limpia archivos temporales antiguos."""
    now = time.time()
    for directory in [UPLOAD_DIR, PROCESSED_DIR]:
        for item in directory.glob("*"):
            if item.is_file():
                try:
                    if now - item.stat().st_mtime > max_age_hours * 3600:
                        item.unlink(missing_ok=True)
                except Exception:
                    pass
