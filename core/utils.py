"""
Shared filesystem paths, filename sanitization, and cleanup helpers for PDF Toolbox.
"""

import shutil
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
UPLOAD_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = BASE_DIR / "processed"

# Ensure working directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def format_bytes(size_bytes: int) -> str:
    """Converts a byte count into a human-readable string (B, KB, MB, GB)."""
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
    """Generates a safe unique filename preserving the original extension."""
    ext = Path(original_name).suffix or ".pdf"
    clean_stem = "".join(c for c in Path(original_name).stem if c.isalnum() or c in ("-", "_"))[:35]
    if not clean_stem:
        clean_stem = "document"
    token = uuid.uuid4().hex[:8]
    if prefix:
        return f"{prefix}_{clean_stem}_{token}{ext}"
    return f"{clean_stem}_{token}{ext}"


def find_local_parent_pdfs() -> List[Dict[str, Any]]:
    """Finds PDF files located in the parent workspace directory."""
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
                    "mtime": stat.st_mtime,
                })
    except OSError:
        pass
    # Sort most recently modified / largest files first
    files.sort(key=lambda x: (-x["mtime"], -x["size_bytes"]))
    return files


def cleanup_old_files(max_age_hours: int = 6) -> None:
    """Removes expired temporary uploads, working directories, and processed files."""
    now = time.time()
    cutoff = max_age_hours * 3600
    for directory in (UPLOAD_DIR, PROCESSED_DIR):
        try:
            for item in directory.iterdir():
                try:
                    if now - item.stat().st_mtime > cutoff:
                        if item.is_file():
                            item.unlink(missing_ok=True)
                        elif item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                except OSError:
                    pass
        except OSError:
            pass


def cleanup_old_tasks(task_store: Dict[str, Dict[str, Any]], max_age_hours: int = 6) -> None:
    """Prunes finished in-memory background task records older than max_age_hours."""
    now = time.time()
    cutoff = max_age_hours * 3600
    expired_ids = [
        tid for tid, info in list(task_store.items())
        if info.get("status") in ("completed", "failed")
        and (now - float(info.get("created_at", now))) > cutoff
    ]
    for tid in expired_ids:
        task_store.pop(tid, None)
