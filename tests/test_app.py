"""
Unit and API integration tests for PDF Toolbox.
Uses synthetic temporary PDFs and images and cleans up generated artifacts after each test.
"""

import io
import shutil
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import app
from core.compressor import COMPRESSION_TASKS
from core.ocr_scanner import OCR_TASKS, prepare_tessdata_dir
from core.operations import parse_page_ranges
from core.utils import PROCESSED_DIR, UPLOAD_DIR
from core.web_to_pdf import (
    build_reader_html_document,
    clean_and_normalize_headings,
    clean_filename_from_title,
    detect_document_language,
    post_clean_extracted_soup,
    pre_clean_html,
)


def make_synthetic_pdf_bytes(num_pages: int = 2, text_prefix: str = "Page") -> bytes:
    doc = pymupdf.open()
    try:
        for i in range(num_pages):
            page = doc.new_page(width=400, height=600)
            page.insert_text((50, 80), f"{text_prefix} {i + 1}", fontsize=16)
        return doc.tobytes()
    finally:
        doc.close()


def make_ocr_test_image_bytes(text: str = "HELLO OCR WORLD") -> bytes:
    img = Image.new("RGB", (600, 180), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((40, 70), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class PdfToolboxTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._before_processed = {p.name for p in PROCESSED_DIR.iterdir()}
        self._before_uploads = {p.name for p in UPLOAD_DIR.iterdir()}

    def tearDown(self):
        for folder, before in ((PROCESSED_DIR, self._before_processed), (UPLOAD_DIR, self._before_uploads)):
            for item in folder.iterdir():
                if item.name not in before:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)

    def test_index_page_english_and_accessible_markup(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text
        self.assertIn('<html lang="en">', html)
        self.assertIn("Compress PDF", html)
        self.assertIn("Digitize / OCR", html)
        self.assertIn("Web to PDF (Zotero)", html)
        self.assertIn('role="tablist"', html)
        self.assertIn('<progress id="progressBar"', html)
        self.assertNotIn("Aligerar PDF", html)
        self.assertNotIn("onclick=", html)

    def test_parse_page_ranges(self):
        self.assertEqual(parse_page_ranges("1-3, 5", 6), [0, 1, 2, 4])
        self.assertEqual(parse_page_ranges("", 3), [0, 1, 2])
        self.assertEqual(parse_page_ranges("99", 3), [])

    def test_split_merge_rotate_inspect_and_metadata(self):
        pdf_3p = make_synthetic_pdf_bytes(3, "Sample")

        # Split
        r_split = self.client.post(
            "/api/split",
            files={"file": ("sample.pdf", pdf_3p, "application/pdf")},
            data={"page_ranges": "1, 3"},
        )
        self.assertEqual(r_split.status_code, 200)
        split_data = r_split.json()
        self.assertEqual(split_data["extracted_pages"], 2)
        self.assertEqual(split_data["page_list"], [1, 3])

        # Download check
        r_dl = self.client.get(f"/api/download/{split_data['filename']}")
        self.assertEqual(r_dl.status_code, 200)
        self.assertEqual(r_dl.headers["content-type"], "application/pdf")

        # Merge
        pdf_1p = make_synthetic_pdf_bytes(1, "Extra")
        r_merge = self.client.post(
            "/api/merge",
            files=[
                ("files", ("a.pdf", pdf_3p, "application/pdf")),
                ("files", ("b.pdf", pdf_1p, "application/pdf")),
            ],
        )
        self.assertEqual(r_merge.status_code, 200)
        self.assertEqual(r_merge.json()["total_pages"], 4)

        # Rotate
        r_rot = self.client.post(
            "/api/rotate",
            files={"file": ("rot.pdf", pdf_3p, "application/pdf")},
            data={"angle": "90", "page_ranges": "1"},
        )
        self.assertEqual(r_rot.status_code, 200)
        self.assertEqual(r_rot.json()["rotated_pages_count"], 1)

        rot_doc = pymupdf.open(r_rot.json()["filepath"])
        try:
            self.assertEqual(rot_doc[0].rotation, 90)
            self.assertEqual(rot_doc[1].rotation, 0)
        finally:
            rot_doc.close()

        # Inspect defaults in English
        r_insp = self.client.post(
            "/api/inspect",
            files={"file": ("insp.pdf", pdf_3p, "application/pdf")},
        )
        self.assertEqual(r_insp.status_code, 200)
        insp_data = r_insp.json()
        self.assertEqual(insp_data["pages"], 3)
        self.assertEqual(insp_data["metadata"]["title"], "Untitled")
        self.assertEqual(insp_data["metadata"]["author"], "Not specified")
        self.assertFalse(insp_data["is_encrypted"])

        # Update Metadata
        r_meta = self.client.post(
            "/api/update-metadata",
            files={"file": ("meta.pdf", pdf_3p, "application/pdf")},
            data={
                "title": "Test Title",
                "author": "Ada Lovelace",
                "subject": "Testing",
                "keywords": "pdf, test",
            },
        )
        self.assertEqual(r_meta.status_code, 200)
        meta_doc = pymupdf.open(r_meta.json()["filepath"])
        try:
            self.assertEqual(meta_doc.metadata["title"], "Test Title")
            self.assertEqual(meta_doc.metadata["author"], "Ada Lovelace")
        finally:
            meta_doc.close()

    def test_async_compression_job(self):
        pdf_bytes = make_synthetic_pdf_bytes(2, "Compress Test")
        res = self.client.post(
            "/api/compress",
            files={"file": ("heavy.pdf", pdf_bytes, "application/pdf")},
            data={"preset": "ebook", "to_grayscale": "false"},
        )
        self.assertEqual(res.status_code, 200)
        task_id = res.json()["task_id"]

        for _ in range(40):
            status_res = self.client.get(f"/api/tasks/{task_id}")
            self.assertEqual(status_res.status_code, 200)
            task = status_res.json()
            if task["status"] in ("completed", "failed"):
                break
            time.sleep(0.15)

        self.assertEqual(COMPRESSION_TASKS[task_id]["status"], "completed")
        out_path = Path(COMPRESSION_TASKS[task_id]["result"]["filepath"])
        self.assertTrue(out_path.is_file())

    def test_ocr_tessdata_resolution_and_scan(self):
        with tempfile.TemporaryDirectory() as td:
            d, _has_osd = prepare_tessdata_dir(Path(td), "eng+spa", auto_orient=True)
            self.assertTrue(Path(d).is_dir())
            with self.assertRaises(FileNotFoundError):
                prepare_tessdata_dir(Path(td) / "missing", "zz_nonexistent", auto_orient=False)

        img_bytes = make_ocr_test_image_bytes("TEST 12345")
        res = self.client.post(
            "/api/ocr-scan",
            files=[("files", ("page1.png", img_bytes, "image/png"))],
            data={"language": "eng", "enhance_contrast": "false", "auto_orient": "false", "custom_title": "OCR Sample"},
        )
        self.assertEqual(res.status_code, 200)
        task_id = res.json()["task_id"]

        for _ in range(60):
            status_res = self.client.get(f"/api/ocr-tasks/{task_id}")
            self.assertEqual(status_res.status_code, 200)
            task = status_res.json()
            if task["status"] in ("completed", "failed"):
                break
            time.sleep(0.2)

        self.assertEqual(OCR_TASKS[task_id]["status"], "completed")
        result = OCR_TASKS[task_id]["result"]
        self.assertTrue(Path(result["filepath"]).is_file())
        self.assertTrue(Path(PROCESSED_DIR / result["text_filename"]).is_file())
        self.assertIn("--- [Page 1] ---", result["text_sample"])

    def test_web_to_pdf_html_cleaning_and_escaping(self):
        raw_html = (
            "<html><body>"
            "<div class='share-buttons'>Share Tweet</div>"
            "<a href='https://twitter.com/intent/tweet?text=hi'>Tweet</a>"
            "<h4>1.</h4><h4>Introduction</h4>"
            "<p><b>Background Overview</b></p>"
            "<p>Body paragraph text with sufficient length.</p>"
            "</body></html>"
        )
        pre_cleaned = pre_clean_html(raw_html)
        self.assertIn("<article>", pre_cleaned)
        self.assertNotIn("share-buttons", pre_cleaned)
        self.assertNotIn("intent/tweet", pre_cleaned)

        soup = BeautifulSoup(
            "<div><script>alert(1)</script><p>Share Tweet Read this</p>"
            "<h4>1.</h4><h4>Introduction</h4><p><b>Subsection</b></p></div>",
            "html.parser",
        )
        post_clean_extracted_soup(soup)
        clean_and_normalize_headings(soup)
        rendered_fragment = str(soup)
        self.assertNotIn("<script>", rendered_fragment)
        self.assertNotIn("Share Tweet", rendered_fragment)
        self.assertIn("<h4>1. Introduction</h4>", rendered_fragment)
        self.assertIn("<h4>Subsection</h4>", rendered_fragment)

        self.assertEqual(detect_document_language("Este es un texto en español de prueba de la página."), "es")
        self.assertEqual(detect_document_language("This is an English document about typography and books."), "en")

        html_doc = build_reader_html_document(
            {
                "title": 'Test <script>alert("x")</script>',
                "author": "Jane & Doe",
                "date": "2026-11-11",
                "url": "https://example.com/post",
                "language": "en",
                "html_body": "<p>Safe body.</p>",
            },
            style="academic",
            zotero_mode="standalone",
        )
        self.assertIn("<title></title>", html_doc)
        self.assertIn("&lt;script&gt;", html_doc)
        self.assertIn("<strong>Author:</strong> Jane &amp; Doe", html_doc)
        self.assertIn("<strong>Date:</strong> 2026-11-11", html_doc)
        self.assertIn("<strong>Source:</strong>", html_doc)

        fname = clean_filename_from_title("Sample: Article?", "Not specified")
        self.assertEqual(fname, "Sample - Article.pdf")

    def test_web_to_pdf_end_to_end_local_server(self):
        img_bytes = make_ocr_test_image_bytes("IMAGEOK")
        sample_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Synthetic Typography Essay</title>
  <meta name="author" content="Grace Hopper">
</head>
<body>
  <div class="share-buttons">Share Tweet</div>
  <article>
    <h1>Synthetic Typography Essay</h1>
    <h4>1.</h4><h4>Foundations</h4>
    <p>Good typography gives hierarchy, rhythm, and clarity to complex technical writing across books and screens.</p>
    <p>Readers benefit from clean spacing, generous line height, and crisp headings when annotating documents in Zotero.</p>
    <img src="/sample.png" alt="Sample diagram">
  </article>
</body>
</html>""".encode("utf-8")

        class LocalHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/sample.png":
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(img_bytes)))
                    self.end_headers()
                    self.wfile.write(img_bytes)
                elif self.path == "/article.html":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(sample_html)))
                    self.end_headers()
                    self.wfile.write(sample_html)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        try:
            # Preview metadata endpoint
            r_meta = self.client.post("/api/web-metadata", data={"url": f"{base_url}/article.html"})
            self.assertEqual(r_meta.status_code, 200)
            meta = r_meta.json()
            self.assertEqual(meta["title"], "Synthetic Typography Essay")
            self.assertEqual(meta["author"], "Grace Hopper")
            self.assertEqual(meta["language"], "en")

            # Convert in standalone Zotero mode
            r_pdf = self.client.post(
                "/api/web-to-pdf",
                data={
                    "url": f"{base_url}/article.html",
                    "mode": "reader",
                    "style": "academic",
                    "include_images": "true",
                    "zotero_mode": "standalone",
                },
            )
            self.assertEqual(r_pdf.status_code, 200, r_pdf.text)
            data = r_pdf.json()
            self.assertTrue(data["success"])
            out_path = Path(data["filepath"])
            self.assertTrue(out_path.is_file())

            doc = pymupdf.open(str(out_path))
            try:
                self.assertGreaterEqual(len(doc), 1)
                self.assertEqual(doc.metadata.get("title", ""), "")
                full_text = "\n".join(page.get_text() for page in doc)
                self.assertIn("1. Foundations", full_text)
                self.assertNotIn("Share Tweet", full_text)
                self.assertGreaterEqual(sum(len(p.get_images()) for p in doc), 1)
            finally:
                doc.close()

            # Convert in parent Zotero mode
            r_parent = self.client.post(
                "/api/web-to-pdf",
                data={
                    "url": f"{base_url}/article.html",
                    "mode": "reader",
                    "style": "sans",
                    "include_images": "false",
                    "zotero_mode": "parent",
                    "custom_title": "Custom Paper Title",
                    "custom_author": "Custom Author",
                },
            )
            self.assertEqual(r_parent.status_code, 200, r_parent.text)
            parent_doc = pymupdf.open(r_parent.json()["filepath"])
            try:
                self.assertEqual(parent_doc.metadata.get("title"), "Custom Paper Title")
                self.assertEqual(parent_doc.metadata.get("author"), "Custom Author")
                self.assertEqual(sum(len(p.get_images()) for p in parent_doc), 0)
            finally:
                parent_doc.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_error_responses(self):
        r_bad_url = self.client.post("/api/web-metadata", data={"url": "ftp://example.com"})
        self.assertEqual(r_bad_url.status_code, 400)

        r_bad_pdf_url = self.client.post("/api/web-to-pdf", data={"url": "not-a-url"})
        self.assertEqual(r_bad_pdf_url.status_code, 400)

        r_no_file = self.client.post("/api/inspect")
        self.assertEqual(r_no_file.status_code, 400)

        r_missing_dl = self.client.get("/api/download/does_not_exist.pdf")
        self.assertEqual(r_missing_dl.status_code, 404)

        r_missing_task = self.client.get("/api/tasks/nonexistent_id")
        self.assertEqual(r_missing_task.status_code, 404)


if __name__ == "__main__":
    unittest.main()
