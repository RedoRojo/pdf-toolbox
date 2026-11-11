import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import pymupdf
from .utils import format_bytes, get_unique_filename, PROCESSED_DIR


def parse_page_ranges(range_str: str, max_pages: int) -> List[int]:
    """
    Parsea una cadena de rangos como '1-5, 8, 10-12' a una lista de índices 0-indexed.
    """
    pages = set()
    parts = [p.strip() for p in range_str.split(",") if p.strip()]
    if not parts:
        return list(range(max_pages))

    for part in parts:
        if "-" in part:
            sub = part.split("-", 1)
            try:
                start = max(1, int(sub[0].strip()))
                end = min(max_pages, int(sub[1].strip()))
                if start <= end:
                    for p in range(start, end + 1):
                        pages.add(p - 1)
            except ValueError:
                continue
        else:
            try:
                p = int(part)
                if 1 <= p <= max_pages:
                    pages.add(p - 1)
            except ValueError:
                continue

    return sorted(list(pages))


def merge_pdfs(file_paths: List[str], output_filename: Optional[str] = None) -> Dict[str, Any]:
    """Une múltiples archivos PDF en un solo documento."""
    if not file_paths:
        raise ValueError("No se proporcionaron archivos para unir.")

    merged_doc = pymupdf.open()
    total_source_pages = 0

    for path in file_paths:
        p = Path(path)
        if not p.is_file():
            continue
        sub_doc = pymupdf.open(str(p))
        merged_doc.insert_pdf(sub_doc)
        total_source_pages += len(sub_doc)
        sub_doc.close()

    if len(merged_doc) == 0:
        raise ValueError("No se pudieron cargar páginas válidas de los archivos.")

    if not output_filename:
        output_filename = get_unique_filename("unido.pdf", prefix="merged")

    out_path = PROCESSED_DIR / output_filename
    merged_doc.save(str(out_path), garbage=4, deflate=True, clean=True)
    merged_doc.close()

    size_bytes = out_path.stat().st_size
    return {
        "success": True,
        "filename": output_filename,
        "filepath": str(out_path),
        "total_pages": total_source_pages,
        "size_bytes": size_bytes,
        "size_formatted": format_bytes(size_bytes),
    }


def split_pdf(input_path: str, page_ranges: str, output_filename: Optional[str] = None) -> Dict[str, Any]:
    """Extrae las páginas seleccionadas de un PDF."""
    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError("Archivo PDF no encontrado.")

    src_doc = pymupdf.open(str(p))
    total_pages = len(src_doc)
    selected_indices = parse_page_ranges(page_ranges, total_pages)

    if not selected_indices:
        src_doc.close()
        raise ValueError(f"No se seleccionaron páginas válidas dentro del rango 1-{total_pages}.")

    new_doc = pymupdf.open()
    for idx in selected_indices:
        new_doc.insert_pdf(src_doc, from_page=idx, to_page=idx)

    if not output_filename:
        output_filename = get_unique_filename(p.name, prefix="dividido")

    out_path = PROCESSED_DIR / output_filename
    new_doc.save(str(out_path), garbage=4, deflate=True, clean=True)
    new_doc.close()
    src_doc.close()

    size_bytes = out_path.stat().st_size
    return {
        "success": True,
        "filename": output_filename,
        "filepath": str(out_path),
        "extracted_pages": len(selected_indices),
        "page_list": [i + 1 for i in selected_indices],
        "size_bytes": size_bytes,
        "size_formatted": format_bytes(size_bytes),
    }


def rotate_pdf(input_path: str, angle: int, page_ranges: Optional[str] = None, output_filename: Optional[str] = None) -> Dict[str, Any]:
    """Rota páginas del PDF en múltiplos de 90 grados (90, 180, 270)."""
    if angle not in (90, 180, 270):
        raise ValueError("El ángulo de rotación debe ser 90, 180 o 270 grados.")

    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError("Archivo PDF no encontrado.")

    doc = pymupdf.open(str(p))
    total_pages = len(doc)
    indices = parse_page_ranges(page_ranges, total_pages) if page_ranges else list(range(total_pages))

    for idx in indices:
        page = doc[idx]
        page.set_rotation((page.rotation + angle) % 360)

    if not output_filename:
        output_filename = get_unique_filename(p.name, prefix=f"rotado_{angle}")

    out_path = PROCESSED_DIR / output_filename
    doc.save(str(out_path), garbage=4, deflate=True)
    doc.close()

    size_bytes = out_path.stat().st_size
    return {
        "success": True,
        "filename": output_filename,
        "filepath": str(out_path),
        "rotated_pages_count": len(indices),
        "angle": angle,
        "size_bytes": size_bytes,
        "size_formatted": format_bytes(size_bytes),
    }


def inspect_pdf(input_path: str) -> Dict[str, Any]:
    """Obtiene metadatos detallados y resumen de estructura de un PDF."""
    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError("Archivo PDF no encontrado.")

    doc = pymupdf.open(str(p))
    total_pages = len(doc)
    stat = p.stat()

    # Dimensiones de la primera página
    dim_str = "N/A"
    first_page_w_pt, first_page_h_pt = 0, 0
    if total_pages > 0:
        rect = doc[0].rect
        first_page_w_pt = round(rect.width, 2)
        first_page_h_pt = round(rect.height, 2)
        # Convertir a mm (1 pt = 25.4 / 72 mm)
        w_mm = round(first_page_w_pt * 25.4 / 72, 1)
        h_mm = round(first_page_h_pt * 25.4 / 72, 1)
        dim_str = f"{w_mm} × {h_mm} mm ({first_page_w_pt} × {first_page_h_pt} pt)"

    # Muestra de imágenes (contar hasta primeras 20 páginas para rapidez)
    sample_images = 0
    pages_to_sample = min(20, total_pages)
    for i in range(pages_to_sample):
        sample_images += len(doc[i].get_images())

    meta = doc.metadata or {}
    doc.close()

    return {
        "success": True,
        "filename": p.name,
        "filesize_bytes": stat.st_size,
        "filesize_formatted": format_bytes(stat.st_size),
        "pages": total_pages,
        "dimensions": dim_str,
        "metadata": {
            "title": meta.get("title") or "Sin título",
            "author": meta.get("author") or "No especificado",
            "subject": meta.get("subject") or "",
            "keywords": meta.get("keywords") or "",
            "creator": meta.get("creator") or "No especificado",
            "producer": meta.get("producer") or "No especificado",
            "creation_date": meta.get("creationDate") or "No especificada",
            "mod_date": meta.get("modDate") or "No especificada",
        },
        "is_encrypted": doc.is_encrypted if hasattr(doc, "is_encrypted") else False,
        "sample_images_first_pages": sample_images,
        "sample_pages_checked": pages_to_sample,
    }


def update_pdf_metadata(
    input_path: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    subject: Optional[str] = None,
    keywords: Optional[str] = None,
    output_filename: Optional[str] = None
) -> Dict[str, Any]:
    """Actualiza los metadatos internos de cualquier archivo PDF."""
    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError("Archivo PDF no encontrado.")

    doc = pymupdf.open(str(p))
    meta = doc.metadata or {}

    if title is not None:
        meta["title"] = title.strip()
    if author is not None:
        meta["author"] = author.strip()
    if subject is not None:
        meta["subject"] = subject.strip()
    if keywords is not None:
        meta["keywords"] = keywords.strip()

    doc.set_metadata(meta)

    if not output_filename:
        output_filename = get_unique_filename(p.name, prefix="meta_editado")

    out_path = PROCESSED_DIR / output_filename
    doc.save(str(out_path), garbage=4, deflate=True)
    doc.close()

    size_bytes = out_path.stat().st_size
    return {
        "success": True,
        "filename": output_filename,
        "filepath": str(out_path),
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "keywords": meta.get("keywords", ""),
        "size_bytes": size_bytes,
        "size_formatted": format_bytes(size_bytes),
    }

