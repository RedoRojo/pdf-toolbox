# PDF Toolbox 📄

Fast, lightweight local toolkit for processing, digitizing, and optimizing PDF files from the **browser** or the **command line**.

## ✨ Features

- **Digitize Book / Document (OCR)**: Converts page photos, scans, or image-only PDFs into **100% selectable, searchable, and copyable PDFs** (Searchable PDF).
  - *Multilingual support*: Spanish (`spa`), English (`eng`), and bilingual (`spa+eng`).
  - *Batch image upload*: Multi-page upload (JPG, PNG, WEBP, TIFF) with automatic natural sorting (`page 1, page 2...`) and thumbnail previews.
  - *Scanned PDFs*: Processes scanned PDFs by adding an invisible selectable text layer to every page.
  - *Image enhancement*: Filter to clean spine/fold shadows and optimize contrast, plus automatic orientation detection.
  - *Dual export*: Download both the searchable PDF and the full `.txt` transcription.
- **Compress PDF**: Reduces the size of heavy documents using Ghostscript and PyMuPDF (`screen` ~72 dpi, `ebook` ~150 dpi, `printer` ~300 dpi, plus grayscale option).
- **Split / Extract**: Extract specific pages and ranges (e.g., `1-10, 25, 40-50`).
- **Merge PDFs**: Combine two or more files into a single ordered PDF.
- **Rotate**: Rotate pages by 90°, 180°, or 270°.
- **Inspect & Edit Metadata**: Inspect dimensions/metadata and update title, author, subject, and keywords.
- **Web to PDF (Articles / Zotero)**: Converts web articles and blog posts into clean PDFs with 100% selectable vector text (`clean` reader mode or `full` page mode).

## 🌐 Web Interface

```bash
# Create environment (first time only)
conda env create -f environment.yml

# Launch web server
./run.sh
```

Opens at `http://127.0.0.1:8000` standalone or `http://127.0.0.1:8002` via **Tools Hub**.

## ⌨️ Command Line Interface

Via the global Tools Hub dispatcher (recommended):

```bash
tools pdf compress report.pdf --preset ebook [--gray] [--dpi 150] [-o out.pdf]
tools pdf merge part1.pdf part2.pdf -o book.pdf
tools pdf split book.pdf --pages "1-10,25,40-50" [-o excerpt.pdf]
tools pdf rotate scan.pdf --angle 90 [--pages "1-3"]
tools pdf inspect report.pdf [--json]
tools pdf meta book.pdf --title "Clean Title" --author "Author Name"
tools pdf ocr page*.jpg --lang spa+eng [--enhance] [--no-orient] [--txt] [-o scan.pdf]
tools pdf web "https://example.com/article" [--mode clean|full] [--no-images] [-o article.pdf]
```

Or standalone from this repository: `./cli.sh <command> ...`.

| Subcommand | Key Options | Description |
| :--- | :--- | :--- |
| `compress` | `--preset screen\|ebook\|printer`, `--gray`, `--dpi N`, `-o` | Compress one or more PDFs synchronously |
| `merge` | `-o merged.pdf` | Merge two or more PDFs in order |
| `split` | `--pages "1-5,8"`, `-o` | Extract pages or page ranges |
| `rotate` | `--angle 90\|180\|270`, `--pages`, `-o` | Rotate selected or all pages |
| `inspect` | `--json` | Show pages, dimensions, encryption, and metadata |
| `meta` | `--title`, `--author`, `--subject`, `--keywords`, `-o` | Edit internal PDF metadata |
| `ocr` | `--lang spa+eng`, `--enhance`, `--no-orient`, `--txt`, `-o` | OCR scanned PDF or images into a searchable PDF |
| `web` | `--mode clean\|full`, `--style`, `--no-images`, `--zotero`, `-o` | Render a web URL into a PDF |

All subcommands write output files to the **current working directory** by default (without overwriting existing files) and support `--json`, `-q/--quiet`, and `-v/--verbose`.

## 🧪 Running Tests

```bash
~/miniconda3/envs/pdf-toolkit/bin/python -m unittest discover -s tests -v
```
