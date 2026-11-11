"""
Core PDF manipulation operations: merge, split, rotate, inspect, and metadata editing.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import pymupdf

from .utils import format_bytes, get_unique_filename, PROCESSED_DIR


def _resolve_out_path(
    output_path: Optional[Union[str, Path]],
    output_filename: Optional[str],
    default_name: str,
    prefix: str = "",
) -> Path:
    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    if not output_filename:
        output_filename = get_unique_filename(default_name, prefix=prefix)
    return PROCESSED_DIR / output_filename


def parse_page_ranges(range_str: str, max_pages: int) -> List[int]:
    """
    Parses a page range string such as '1-5, 8, 10-12' into a sorted list of 0-based page indices.
    """
    pages = set()
    parts = [p.strip() for p in range_str.split(",") if p.strip()]
    if not parts:
        return list(range(max_pages))

    for part in parts:
        if "-" in part:
            sub = part.split("-", 1)
            try:
                start = int(sub[0].strip())
                end = int(sub[1].strip())
                if start < 1 and end < 1:
                    continue
                if start > max_pages and end > max_pages:
                    continue
                clamped_start = max(1, start)
                clamped_end = min(max_pages, end)
                if clamped_start <= clamped_end:
                    for p in range(clamped_start, clamped_end + 1):
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

    return sorted(pages)


def merge_pdfs(
    file_paths: List[str],
    output_filename: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Merges multiple PDF files into a single document in sequence."""
    if not file_paths:
        raise ValueError("No files provided to merge.")

    merged_doc = pymupdf.open()
    total_source_pages = 0

    try:
        for path in file_paths:
            p = Path(path)
            if not p.is_file():
                continue
            sub_doc = pymupdf.open(str(p))
            try:
                if sub_doc.needs_pass:
                    raise ValueError(f"File '{p.name}' is password-protected and cannot be merged.")
                merged_doc.insert_pdf(sub_doc)
                total_source_pages += len(sub_doc)
            finally:
                sub_doc.close()

        if len(merged_doc) == 0:
            raise ValueError("Could not load valid pages from the provided files.")

        out_path = _resolve_out_path(output_path, output_filename, "merged.pdf", prefix="merged")
        merged_doc.save(str(out_path), garbage=4, deflate=True, clean=True)
    finally:
        merged_doc.close()

    size_bytes = out_path.stat().st_size
    return {
        "success": True,
        "filename": out_path.name,
        "filepath": str(out_path),
        "total_pages": total_source_pages,
        "size_bytes": size_bytes,
        "size_formatted": format_bytes(size_bytes),
    }


def split_pdf(
    input_path: str,
    page_ranges: str,
    output_filename: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Extracts selected pages from a PDF document."""
    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError("PDF file not found.")

    src_doc = pymupdf.open(str(p))
    try:
        if src_doc.needs_pass:
            raise ValueError("This PDF is password-protected and cannot be split.")

        total_pages = len(src_doc)
        selected_indices = parse_page_ranges(page_ranges, total_pages)

        if not selected_indices:
            raise ValueError(f"No valid pages selected within range 1-{total_pages}.")

        new_doc = pymupdf.open()
        try:
            for idx in selected_indices:
                new_doc.insert_pdf(src_doc, from_page=idx, to_page=idx)

            out_path = _resolve_out_path(output_path, output_filename, p.name, prefix="split")
            new_doc.save(str(out_path), garbage=4, deflate=True, clean=True)
        finally:
            new_doc.close()
    finally:
        src_doc.close()

    size_bytes = out_path.stat().st_size
    return {
        "success": True,
        "filename": out_path.name,
        "filepath": str(out_path),
        "extracted_pages": len(selected_indices),
        "page_list": [i + 1 for i in selected_indices],
        "size_bytes": size_bytes,
        "size_formatted": format_bytes(size_bytes),
    }


def rotate_pdf(
    input_path: str,
    angle: int,
    page_ranges: Optional[str] = None,
    output_filename: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Rotates PDF pages by multiples of 90 degrees (90, 180, or 270)."""
    if angle not in (90, 180, 270):
        raise ValueError("Rotation angle must be 90, 180, or 270 degrees.")

    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError("PDF file not found.")

    doc = pymupdf.open(str(p))
    try:
        if doc.needs_pass:
            raise ValueError("This PDF is password-protected and cannot be rotated.")

        total_pages = len(doc)
        if page_ranges and page_ranges.strip():
            indices = parse_page_ranges(page_ranges, total_pages)
            if not indices:
                raise ValueError(f"No valid pages selected within range 1-{total_pages}.")
        else:
            indices = list(range(total_pages))

        for idx in indices:
            page = doc[idx]
            page.set_rotation((page.rotation + angle) % 360)

        out_path = _resolve_out_path(output_path, output_filename, p.name, prefix=f"rotated_{angle}")
        doc.save(str(out_path), garbage=4, deflate=True)
    finally:
        doc.close()

    size_bytes = out_path.stat().st_size
    return {
        "success": True,
        "filename": out_path.name,
        "filepath": str(out_path),
        "rotated_pages_count": len(indices),
        "angle": angle,
        "size_bytes": size_bytes,
        "size_formatted": format_bytes(size_bytes),
    }


def inspect_pdf(input_path: str) -> Dict[str, Any]:
    """Retrieves detailed metadata, dimensions, and structure summary for a PDF."""
    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError("PDF file not found.")

    stat = p.stat()
    doc = pymupdf.open(str(p))
    try:
        total_pages = len(doc)
        is_encrypted = bool(doc.is_encrypted)
        meta = doc.metadata or {}

        dim_str = "N/A"
        if total_pages > 0 and not doc.needs_pass:
            rect = doc[0].rect
            first_page_w_pt = round(rect.width, 2)
            first_page_h_pt = round(rect.height, 2)
            w_mm = round(first_page_w_pt * 25.4 / 72, 1)
            h_mm = round(first_page_h_pt * 25.4 / 72, 1)
            dim_str = f"{w_mm} × {h_mm} mm ({first_page_w_pt} × {first_page_h_pt} pt)"

        sample_images = 0
        pages_to_sample = min(20, total_pages) if not doc.needs_pass else 0
        for i in range(pages_to_sample):
            sample_images += len(doc[i].get_images())
    finally:
        doc.close()

    return {
        "success": True,
        "filename": p.name,
        "filesize_bytes": stat.st_size,
        "filesize_formatted": format_bytes(stat.st_size),
        "pages": total_pages,
        "dimensions": dim_str,
        "metadata": {
            "title": meta.get("title") or "Untitled",
            "author": meta.get("author") or "Not specified",
            "subject": meta.get("subject") or "",
            "keywords": meta.get("keywords") or "",
            "creator": meta.get("creator") or "Not specified",
            "producer": meta.get("producer") or "Not specified",
            "creation_date": meta.get("creationDate") or "Not specified",
            "mod_date": meta.get("modDate") or "Not specified",
        },
        "is_encrypted": is_encrypted,
        "sample_images_first_pages": sample_images,
        "sample_pages_checked": pages_to_sample,
    }


def update_pdf_metadata(
    input_path: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    subject: Optional[str] = None,
    keywords: Optional[str] = None,
    output_filename: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Updates internal PDF metadata fields cleanly."""
    p = Path(input_path)
    if not p.is_file():
        raise FileNotFoundError("PDF file not found.")

    doc = pymupdf.open(str(p))
    try:
        if doc.needs_pass:
            raise ValueError("This PDF is password-protected and cannot be modified.")

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

        out_path = _resolve_out_path(output_path, output_filename, p.name, prefix="meta_edited")
        doc.save(str(out_path), garbage=4, deflate=True)
    finally:
        doc.close()

    size_bytes = out_path.stat().st_size
    return {
        "success": True,
        "filename": out_path.name,
        "filepath": str(out_path),
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "keywords": meta.get("keywords", ""),
        "size_bytes": size_bytes,
        "size_formatted": format_bytes(size_bytes),
    }
