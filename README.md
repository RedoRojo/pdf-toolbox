# PDF Toolbox

Fast, lightweight local web toolkit with a clean, minimalist interface for processing, digitizing, and optimizing PDF files.

## Features

- **Compress PDF**: Reduces heavy document file sizes using Ghostscript and PyMuPDF:
  - *Maximum Compression* (~72 dpi)
  - *Balanced / Recommended* (~150 dpi)
  - *High Quality* (~300 dpi)
  - *Grayscale option* for maximum savings on scanned documents or books.
- **Digitize Book / Document (OCR)**: Converts page photos, scans, or image-only PDFs into **100% selectable, searchable, and copyable PDFs**.
  - *Multilingual support*: English (`eng`), English + Spanish (`eng+spa`), and Spanish (`spa`).
  - *Batch image upload*: Multi-page upload (JPG, PNG, WEBP, TIFF, BMP) with natural filename sorting and thumbnail previews.
  - *Scanned PDFs*: Adds an invisible selectable text layer to every page.
  - *Image enhancement*: Contrast optimization and automatic orientation detection.
  - *Dual export*: Download both the searchable PDF and the `.txt` transcription with one-click clipboard copy.
- **Web to PDF (Articles / Zotero)**: Converts web articles and blog posts into clean PDFs with 100% selectable vector text.
  - *Zotero Direct PDF File mode*: Strips internal document metadata so Zotero imports the file cleanly as a top-level PDF without creating nested container items.
  - *Bibliographic Record mode*: Embeds full title, author, subject, and source URL metadata.
  - *Clean Article Mode*: Removes ads, banners, and social share blocks, normalizes headings for legacy HTML archives, and embeds images inline.
  - *Full Page Snapshot Mode*: Captures the entire webpage preserving original styles.
- **Split / Extract**: Extract specific pages and ranges (e.g., `1-10, 25, 40-50`).
- **Merge PDFs**: Combine two or more PDF files in order.
- **Rotate**: Rotate all or selected pages by 90°, 180°, or 270°.
- **Inspect & Edit Metadata**: View page count, dimensions, and PDF metadata, and update title, author, subject, or keywords cleanly.

## Requirements

### System Dependencies

- **Ghostscript** (`gs`): Used as the primary PDF compression engine (falls back cleanly to PyMuPDF if unavailable).
- **Tesseract OCR** (`tesseract`): Required for the OCR Digitizer tab (`tesseract-ocr` + language packs such as `eng` and `spa`).
- **Chromium-based Browser** (Chrome, Chromium, Helium, Brave, or Edge): Required for rendering Web-to-PDF documents via headless printing.

### Python Environment

Using Miniconda (recommended):

```bash
# Create environment (first time only)
conda env create -f environment.yml

# Launch server
./run.sh
```

Or using `venv` + `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

You can also override the Python interpreter path via `PDF_TOOLBOX_PYTHON=/path/to/python ./run.sh`.

Open your browser at the URL printed in the terminal (defaults to `http://127.0.0.1:8000` standalone or `http://127.0.0.1:8002` via **Tools Hub**).

## Running Tests

```bash
python -m unittest discover -s tests
```
