#!/usr/bin/env python3
"""
PDF Toolbox - Command Line Interface.

Thin synchronous adapter over core/: compress, merge, split, rotate, inspect,
ocr, web-to-pdf, and metadata editing. Never imports app.py or FastAPI.

Examples:
    tools pdf compress report.pdf --preset ebook
    tools pdf merge a.pdf b.pdf -o combined.pdf
    tools pdf split book.pdf --pages "1-10,25"
    tools pdf rotate scan.pdf --angle 90
    tools pdf inspect report.pdf --json
    tools pdf ocr page*.jpg --lang spa+eng --enhance
    tools pdf web "https://example.com/article" -o article.pdf
    tools pdf meta book.pdf --title "Clean Title" --author "Author"
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

__version__ = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

PROG = os.environ.get("TOOLS_PROG", "cli.sh")
EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_INTERRUPTED = 0, 1, 2, 130


class CLIError(Exception):
    """Expected runtime error: printed without a traceback, exits with code 1."""


def log(args, message: str) -> None:
    if not getattr(args, "quiet", False):
        print(message, file=sys.stderr, flush=True)


def emit(args, payload: dict, human: str) -> None:
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif human:
        print(human)


def resolve_output(requested: Optional[str], default_name: str) -> Path:
    """Explicit -o is used as-is (dirs get default_name); otherwise write to cwd without overwriting."""
    if requested:
        path = Path(requested).expanduser()
        if path.is_dir():
            path = path / default_name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    path = Path.cwd() / default_name
    stem, suffix, counter = path.stem, path.suffix, 1
    while path.exists():
        path = path.with_name(f"{stem}-{counter}{suffix}")
        counter += 1
    return path.resolve()


def require_file(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_file():
        raise CLIError(f"file not found: {path_str}")
    return p.resolve()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_compress(args) -> int:
    from core.compressor import compress_pdf

    inputs = [require_file(f) for f in args.files]
    if len(inputs) > 1 and args.output and not Path(args.output).expanduser().is_dir():
        raise CLIError("when compressing multiple files, -o must be a directory (or omitted).")

    results = []
    human_lines = []
    for in_path in inputs:
        default_name = f"{in_path.stem}-compressed.pdf"
        out_path = resolve_output(args.output, default_name)

        def _prog(pct: int, msg: str) -> None:
            log(args, f"[{in_path.name}] {pct}% - {msg}")

        try:
            res = compress_pdf(
                input_path=str(in_path),
                output_path=out_path,
                preset=args.preset,
                to_grayscale=args.gray,
                custom_dpi=args.dpi,
                progress_cb=_prog,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            raise CLIError(str(e))

        log(
            args,
            f"Compressed {in_path.name}: {res['original_size_formatted']} -> "
            f"{res['compressed_size_formatted']} ({res['saved_percentage']}% saved)",
        )
        results.append(res)
        human_lines.append(res["filepath"])

    payload = results[0] if len(results) == 1 else {"items": results, "count": len(results)}
    emit(args, payload, "\n".join(human_lines))
    return EXIT_OK


def cmd_merge(args) -> int:
    from core.operations import merge_pdfs

    if len(args.files) < 2:
        raise CLIError("merge requires at least 2 input PDF files.")
    inputs = [str(require_file(f)) for f in args.files]
    out_path = resolve_output(args.output, "merged.pdf")
    try:
        res = merge_pdfs(inputs, output_path=out_path)
    except (FileNotFoundError, ValueError) as e:
        raise CLIError(str(e))
    log(args, f"Merged {len(inputs)} files ({res['total_pages']} pages, {res['size_formatted']}):")
    emit(args, res, res["filepath"])
    return EXIT_OK


def cmd_split(args) -> int:
    from core.operations import split_pdf

    in_path = require_file(args.file)
    out_path = resolve_output(args.output, f"{in_path.stem}-split.pdf")
    try:
        res = split_pdf(str(in_path), args.pages, output_path=out_path)
    except (FileNotFoundError, ValueError) as e:
        raise CLIError(str(e))
    log(args, f"Extracted {res['extracted_pages']} page(s) ({res['size_formatted']}):")
    emit(args, res, res["filepath"])
    return EXIT_OK


def cmd_rotate(args) -> int:
    from core.operations import rotate_pdf

    in_path = require_file(args.file)
    out_path = resolve_output(args.output, f"{in_path.stem}-rotated-{args.angle}.pdf")
    try:
        res = rotate_pdf(str(in_path), args.angle, page_ranges=args.pages, output_path=out_path)
    except (FileNotFoundError, ValueError) as e:
        raise CLIError(str(e))
    log(args, f"Rotated {res['rotated_pages_count']} page(s) by {args.angle}° ({res['size_formatted']}):")
    emit(args, res, res["filepath"])
    return EXIT_OK


def cmd_inspect(args) -> int:
    from core.operations import inspect_pdf

    inputs = [require_file(f) for f in args.files]
    results = []
    human_blocks: List[str] = []
    for in_path in inputs:
        try:
            res = inspect_pdf(str(in_path))
        except (FileNotFoundError, ValueError) as e:
            raise CLIError(str(e))
        res["filepath"] = str(in_path)
        results.append(res)
        meta = res["metadata"]
        human_blocks.append(
            f"File:       {res['filename']} ({res['filesize_formatted']})\n"
            f"Pages:      {res['pages']}\n"
            f"Dimensions: {res['dimensions']}\n"
            f"Encrypted:  {res['is_encrypted']}\n"
            f"Title:      {meta['title']}\n"
            f"Author:     {meta['author']}"
        )

    payload = results[0] if len(results) == 1 else {"items": results, "count": len(results)}
    emit(args, payload, "\n\n".join(human_blocks))
    return EXIT_OK


def cmd_meta(args) -> int:
    from core.operations import update_pdf_metadata

    if all(v is None for v in (args.title, args.author, args.subject, args.keywords)):
        raise CLIError("provide at least one metadata flag (--title, --author, --subject, or --keywords).")

    in_path = require_file(args.file)
    out_path = resolve_output(args.output, f"{in_path.stem}-meta.pdf")
    try:
        res = update_pdf_metadata(
            str(in_path),
            title=args.title,
            author=args.author,
            subject=args.subject,
            keywords=args.keywords,
            output_path=out_path,
        )
    except (FileNotFoundError, ValueError) as e:
        raise CLIError(str(e))
    log(args, f"Updated metadata for {in_path.name} ({res['size_formatted']}):")
    emit(args, res, res["filepath"])
    return EXIT_OK


def cmd_ocr(args) -> int:
    from core.ocr_scanner import ocr_scan

    inputs = [str(require_file(f)) for f in args.files]
    first_stem = Path(inputs[0]).stem
    default_name = f"{args.title.strip().replace(' ', '-') if args.title else first_stem}-ocr.pdf"
    out_pdf = resolve_output(args.output, default_name)
    out_txt = out_pdf.with_suffix(".txt") if args.txt else None

    def _prog(pct: int, msg: str, cur: int, tot: int) -> None:
        log(args, f"[OCR {pct}%] {msg}")

    try:
        res = ocr_scan(
            input_paths=inputs,
            output_path=out_pdf,
            txt_output_path=out_txt,
            language=args.lang,
            enhance_contrast=args.enhance,
            auto_orient=not args.no_orient,
            custom_title=args.title,
            write_txt=bool(args.txt),
            progress_cb=_prog,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        raise CLIError(str(e))

    human = res["filepath"]
    if args.txt and res.get("text_filepath"):
        human += f"\n{res['text_filepath']}"
    emit(args, res, human)
    return EXIT_OK


def cmd_web(args) -> int:
    from core.web_to_pdf import convert_web_to_pdf, clean_filename_from_title

    url = args.url.strip()
    if not url.startswith(("http://", "https://")):
        raise CLIError("invalid URL: must start with http:// or https://")

    mode_map = {"clean": "reader", "reader": "reader", "full": "fullpage", "fullpage": "fullpage"}
    internal_mode = mode_map[args.mode]

    # Resolve target path: if -o is given, use it; otherwise let convert_web_to_pdf build the title first
    explicit_out = resolve_output(args.output, "web-article.pdf") if args.output else None
    log(args, f"Converting {url} (mode={internal_mode})...")
    try:
        res = convert_web_to_pdf(
            url=url,
            mode=internal_mode,
            style=args.style,
            include_images=not args.no_images,
            custom_title=args.title,
            custom_author=args.author,
            zotero_mode=args.zotero,
            output_path=explicit_out,
        )
        if explicit_out is None:
            # Move from PROCESSED_DIR into cwd without overwriting
            src = Path(res["filepath"])
            dest = resolve_output(None, clean_filename_from_title(res["title"], res.get("author")))
            src.replace(dest)
            res["filepath"] = str(dest)
            res["filename"] = dest.name
    except Exception as e:
        raise CLIError(str(e))

    log(args, f"Saved {res['pages']} page(s) ({res['filesize_formatted']}):")
    emit(args, res, res["filepath"])
    return EXIT_OK


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def add_common_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="print machine-readable JSON to stdout")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress progress messages on stderr")
    p.add_argument("-v", "--verbose", action="store_true", help="show full tracebacks on errors")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="PDF Toolbox CLI — compress, merge, split, rotate, inspect, OCR, and convert web articles to PDF.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # compress
    p_comp = sub.add_parser("compress", help="compress one or more PDF files")
    p_comp.add_argument("files", nargs="+", help="input PDF file(s)")
    p_comp.add_argument("--preset", choices=("screen", "ebook", "printer"), default="ebook",
                        help="compression preset (default: ebook)")
    p_comp.add_argument("--gray", action="store_true", help="convert colors to grayscale")
    p_comp.add_argument("--dpi", type=int, help="override target image DPI (50-600)")
    p_comp.add_argument("-o", "--output", help="output PDF file (or directory for batch)")
    add_common_flags(p_comp)
    p_comp.set_defaults(func=cmd_compress)

    # merge
    p_merge = sub.add_parser("merge", help="merge two or more PDF files into one")
    p_merge.add_argument("files", nargs="+", help="input PDF files in order")
    p_merge.add_argument("-o", "--output", help="output PDF file (default: ./merged.pdf)")
    add_common_flags(p_merge)
    p_merge.set_defaults(func=cmd_merge)

    # split
    p_split = sub.add_parser("split", help="extract pages or page ranges from a PDF")
    p_split.add_argument("file", help="input PDF file")
    p_split.add_argument("--pages", required=True, help="page ranges, e.g. '1-5,8,10-12'")
    p_split.add_argument("-o", "--output", help="output PDF file")
    add_common_flags(p_split)
    p_split.set_defaults(func=cmd_split)

    # rotate
    p_rot = sub.add_parser("rotate", help="rotate pages in a PDF by 90, 180, or 270 degrees")
    p_rot.add_argument("file", help="input PDF file")
    p_rot.add_argument("--angle", type=int, choices=(90, 180, 270), required=True, help="rotation angle")
    p_rot.add_argument("--pages", help="optional page ranges to rotate (default: all pages)")
    p_rot.add_argument("-o", "--output", help="output PDF file")
    add_common_flags(p_rot)
    p_rot.set_defaults(func=cmd_rotate)

    # inspect
    p_insp = sub.add_parser("inspect", help="inspect metadata, page count, and dimensions of PDF(s)")
    p_insp.add_argument("files", nargs="+", help="input PDF file(s)")
    add_common_flags(p_insp)
    p_insp.set_defaults(func=cmd_inspect)

    # meta
    p_meta = sub.add_parser("meta", help="update internal PDF metadata fields")
    p_meta.add_argument("file", help="input PDF file")
    p_meta.add_argument("--title", help="new document title")
    p_meta.add_argument("--author", help="new document author")
    p_meta.add_argument("--subject", help="new document subject")
    p_meta.add_argument("--keywords", help="new document keywords")
    p_meta.add_argument("-o", "--output", help="output PDF file")
    add_common_flags(p_meta)
    p_meta.set_defaults(func=cmd_meta)

    # ocr
    p_ocr = sub.add_parser("ocr", help="run Tesseract OCR on a scanned PDF or page images")
    p_ocr.add_argument("files", nargs="+", help="one PDF or one/more page images (JPG, PNG, WEBP, TIFF)")
    p_ocr.add_argument("--lang", default="spa+eng", help="Tesseract language code(s) (default: spa+eng)")
    p_ocr.add_argument("--enhance", action="store_true", help="enhance contrast and clean page shadows")
    p_ocr.add_argument("--no-orient", action="store_true", help="disable automatic page orientation detection")
    p_ocr.add_argument("--title", help="document title metadata")
    p_ocr.add_argument("--txt", action="store_true", help="also save extracted plain text (.txt) alongside the PDF")
    p_ocr.add_argument("-o", "--output", help="output searchable PDF file")
    add_common_flags(p_ocr)
    p_ocr.set_defaults(func=cmd_ocr)

    # web
    p_web = sub.add_parser("web", help="convert a web article or page into a clean PDF")
    p_web.add_argument("url", help="source http(s) URL")
    p_web.add_argument("--mode", choices=("clean", "full", "reader", "fullpage"), default="clean",
                       help="clean article mode or full webpage render (default: clean)")
    p_web.add_argument("--style", choices=("academic", "modern", "sans"), default="academic",
                       help="typography style for clean mode (default: academic)")
    p_web.add_argument("--no-images", action="store_true", help="strip article images in clean mode")
    p_web.add_argument("--title", help="override article title")
    p_web.add_argument("--author", help="override article author")
    p_web.add_argument("--zotero", choices=("standalone", "parent"), default="standalone",
                       help="metadata profile for Zotero (default: standalone)")
    p_web.add_argument("-o", "--output", help="output PDF file")
    add_common_flags(p_web)
    p_web.set_defaults(func=cmd_web)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return EXIT_USAGE

    try:
        return args.func(args) or EXIT_OK
    except CLIError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception as e:
        if getattr(args, "verbose", False):
            raise
        print(f"error: {e} (use -v for details)", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
