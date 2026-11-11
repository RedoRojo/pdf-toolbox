# Agent Guide — PDF Toolbox (`tools pdf`)

Fast reference for AI agents invoking or maintaining `pdf-toolbox`.

## 1. Invoking from an Agent

- **Never start the web server (`./run.sh`)** to process PDFs. Always invoke `tools pdf` (or `./cli.sh`).
- **Always pass `--json -q`** for machine-readable JSON on `stdout` and no progress noise on `stderr`.
- **Default output location**: current working directory (auto-incremented filename so existing files are never overwritten). Pass `-o <path>` to write to a specific file or directory.
- **Exit codes**: `0` = success, `1` = runtime error, `2` = usage error.

### Common Recipes

```bash
# 1. Inspect metadata, page count, dimensions, and encryption status
tools pdf inspect document.pdf --json -q

# 2. Compress PDF (presets: screen ~72dpi, ebook ~150dpi [default], printer ~300dpi)
tools pdf compress document.pdf --preset ebook --json -q
tools pdf compress scanned.pdf --preset screen --gray -o compact.pdf --json -q

# 3. Merge multiple PDFs in order
tools pdf merge part1.pdf part2.pdf part3.pdf -o combined.pdf --json -q

# 4. Split / extract specific pages or ranges (1-indexed, inclusive)
tools pdf split book.pdf --pages "1-10,25,40-50" -o excerpt.pdf --json -q

# 5. Rotate pages (90, 180, or 270 degrees; omit --pages to rotate all pages)
tools pdf rotate scan.pdf --angle 90 --pages "1-3" -o rotated.pdf --json -q

# 6. Edit internal PDF metadata
tools pdf meta book.pdf --title "Clean Title" --author "Author Name" -o titled.pdf --json -q

# 7. OCR a scanned PDF or a batch of page images into a searchable PDF (+ optional .txt)
tools pdf ocr page1.jpg page2.jpg --lang spa+eng --enhance --txt -o searchable.pdf --json -q

# 8. Convert a web article or full webpage to PDF
tools pdf web "https://example.com/article" --mode clean --style academic -o article.pdf --json -q
```

### JSON Output Schemas (`--json`)

- **`inspect`**:
  ```json
  {
    "success": true,
    "filename": "doc.pdf",
    "filepath": "/abs/path/doc.pdf",
    "filesize_bytes": 14200,
    "filesize_formatted": "13.87 KB",
    "pages": 12,
    "dimensions": "210.0 × 297.0 mm (595.28 × 841.89 pt)",
    "metadata": { "title": "...", "author": "...", "subject": "", "keywords": "" },
    "is_encrypted": false
  }
  ```
- **`compress`**: `{ "filename", "filepath", "original_size_bytes", "compressed_size_bytes", "saved_bytes", "saved_percentage", "duration_seconds", "preset", "to_grayscale" }`
- **`merge` / `split` / `rotate` / `meta`**: `{ "success": true, "filename", "filepath", "size_bytes", "size_formatted", ... }`
- **`ocr`**: `{ "filename", "filepath", "text_filename", "text_filepath", "total_pages", "language", "pdf_size_bytes", "txt_size_bytes", "duration_seconds", "text_sample" }`
- **`web`**: `{ "success": true, "filename", "filepath", "title", "author", "pages", "filesize_bytes", "mode" }`

## 2. Codebase Map

- `core/operations.py`: `merge_pdfs`, `split_pdf`, `rotate_pdf`, `inspect_pdf`, `update_pdf_metadata`.
- `core/compressor.py`: Synchronous `compress_pdf` + background wrapper `start_compression_job`.
- `core/ocr_scanner.py`: Synchronous `ocr_scan` + background wrapper `start_ocr_job`.
- `core/web_to_pdf.py`: `convert_web_to_pdf`, `fetch_web_metadata`, `extract_article_content`.
- `cli.py` / `cli.sh`: CLI adapter (`argparse`). Uses Miniconda env `~/miniconda3/envs/pdf-toolkit`.
- `tests/`: Run with `~/miniconda3/envs/pdf-toolkit/bin/python -m unittest discover -s tests -v`.
