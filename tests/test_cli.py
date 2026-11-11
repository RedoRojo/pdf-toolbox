"""
CLI tests for PDF Toolbox. Standard library unittest + subprocess.
Run with:
    ~/miniconda3/envs/pdf-toolkit/bin/python -m unittest discover -s tests -v
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

BASE_DIR = Path(__file__).resolve().parent.parent
CLI = BASE_DIR / "cli.py"


def run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
    )


def make_sample_pdf(path: Path, pages: int = 3, title: str = "Sample Doc") -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Hello from page {i + 1} of {title}")
    doc.set_metadata({"title": title, "author": "Tester"})
    doc.save(str(path))
    doc.close()
    return path


class PDFToolboxCLITests(unittest.TestCase):
    def test_help_for_all_subcommands(self):
        for sub in ([], ["compress"], ["merge"], ["split"], ["rotate"], ["inspect"], ["meta"], ["ocr"], ["web"]):
            res = run_cli(*sub, "--help")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("usage:", res.stdout)

    def test_no_command_exits_with_usage_code(self):
        self.assertEqual(run_cli().returncode, 2)

    def test_inspect_human_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_sample_pdf(Path(tmp) / "doc.pdf", pages=2, title="My Title")
            res = run_cli("inspect", str(p), "--json", cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["pages"], 2)
            self.assertEqual(data["metadata"]["title"], "My Title")

    def test_split_rotate_merge_and_meta_in_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            a = make_sample_pdf(tmp_path / "a.pdf", pages=3)
            b = make_sample_pdf(tmp_path / "b.pdf", pages=2)

            # split
            r_split = run_cli("split", str(a), "--pages", "1,3", "--json", cwd=tmp)
            self.assertEqual(r_split.returncode, 0, r_split.stderr)
            split_payload = json.loads(r_split.stdout)
            self.assertEqual(split_payload["extracted_pages"], 2)
            self.assertEqual(Path(split_payload["filepath"]).parent, tmp_path)

            # rotate
            r_rot = run_cli("rotate", str(a), "--angle", "90", "--pages", "1-2", "--json", cwd=tmp)
            self.assertEqual(r_rot.returncode, 0, r_rot.stderr)
            rot_payload = json.loads(r_rot.stdout)
            self.assertEqual(rot_payload["rotated_pages_count"], 2)

            # merge
            r_merge = run_cli("merge", str(a), str(b), "--json", cwd=tmp)
            self.assertEqual(r_merge.returncode, 0, r_merge.stderr)
            merge_payload = json.loads(r_merge.stdout)
            self.assertEqual(merge_payload["total_pages"], 5)
            self.assertEqual(Path(merge_payload["filepath"]).name, "merged.pdf")

            # second merge does not overwrite merged.pdf
            r_merge2 = run_cli("merge", str(a), str(b), cwd=tmp)
            self.assertEqual(r_merge2.returncode, 0, r_merge2.stderr)
            self.assertEqual(Path(r_merge2.stdout.strip()).name, "merged-1.pdf")

            # meta
            r_meta = run_cli("meta", str(a), "--title", "Updated Title", "--author", "Ada", "--json", cwd=tmp)
            self.assertEqual(r_meta.returncode, 0, r_meta.stderr)
            meta_payload = json.loads(r_meta.stdout)
            self.assertEqual(meta_payload["title"], "Updated Title")
            self.assertEqual(meta_payload["author"], "Ada")

    def test_compress_runs_synchronously(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_sample_pdf(Path(tmp) / "orig.pdf", pages=2)
            res = run_cli("compress", str(p), "--preset", "ebook", "--json", cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            payload = json.loads(res.stdout)
            self.assertTrue(Path(payload["filepath"]).is_file())
            self.assertGreater(payload["compressed_size_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
