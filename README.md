# PDF Toolbox 📄

Fast, lightweight local web toolkit with a clean, minimalist interface for processing, digitizing, and optimizing PDF files.

## ✨ Features

- **Digitize Book / Document (OCR)**: Converts page photos, scans, or image-only PDFs into **100% selectable, searchable, and copyable PDFs** (Searchable PDF).
  - *Multilingual support*: Spanish (`spa`), English (`eng`), and bilingual (`spa+eng`).
  - *Batch image upload*: Multi-page upload (JPG, PNG, WEBP, TIFF) with automatic natural sorting (`page 1, page 2...`) and thumbnail previews.
  - *Scanned PDFs*: Processes scanned PDFs by adding an invisible selectable text layer to every page.
  - *Image enhancement*: Filter to clean spine/fold shadows and optimize contrast, plus automatic orientation detection.
  - *Dual export*: Download both the searchable PDF and the full `.txt` transcription with one-click clipboard copy.
- **Compress PDF**: Reduces the size of heavy documents using Ghostscript and PyMuPDF:
  - *Maximum compression* (~72 dpi)
  - *Balanced / Recommended* (~150 dpi)
  - *High quality* (~300 dpi)
  - *Grayscale option* (maximum space savings for scanned documents or books).
- **Split / Extract**: Extract specific pages and ranges (e.g., `1-10, 25, 40-50`).
- **Merge PDFs**: Combine two or more files into a single ordered PDF.
- **Rotate**: Rotate pages by 90°, 180°, or 270°.
- **Inspect**: Detailed analysis of metadata, resolution, and page dimensions.
- **Web to PDF (Articles / Zotero)**: Converts web articles and blog posts into clean PDFs with 100% selectable vector text.
  - *Clean Article Mode*: Strips cookie banners, ads, and sidebars, applying editorial typography ideal for reading and highlighting in Zotero.
  - *Zotero Metadata*: Automatically embeds title, author, date, and source URL.
  - *Full Page Mode*: Captures the full webpage preserving original styles.

## 🚀 Requirements & Conda Environment

This project uses a dedicated Miniconda environment (`pdf-toolkit` with Python 3.12).
To run it:

```bash
# Create environment (first time only)
conda env create -f environment.yml

# Launch server
./run.sh
```

Open your browser at the URL shown in the terminal (defaults to `http://127.0.0.1:8000` standalone or `http://127.0.0.1:8002` via **Tools Hub**).
