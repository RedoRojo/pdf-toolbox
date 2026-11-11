"""
Web-to-PDF conversion module tailored for clean reading and Zotero annotation workflows.
Extracts structured web articles, cleans clutter, normalizes headings, embeds images as
Data URIs, and renders selectable vector PDFs using a headless Chromium-based browser.
"""

import base64
from html import escape as html_escape
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
import pymupdf
import trafilatura
from bs4 import BeautifulSoup

from .utils import PROCESSED_DIR

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def find_browser_binary() -> str:
    """Locates a Chromium-based browser executable installed on the system."""
    candidates = [
        "/usr/bin/helium-browser",
        "/opt/helium-browser-bin/chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("helium-browser"),
        shutil.which("brave-browser"),
        shutil.which("microsoft-edge"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise RuntimeError(
        "No Chromium-based browser (Chrome, Chromium, Helium, Brave, or Edge) was found for PDF rendering."
    )


def detect_document_language(text_or_html: str, soup: Optional[BeautifulSoup] = None) -> str:
    """
    Detects the primary document language (e.g., 'en', 'es', 'fr') from HTML attributes
    or lightweight stopword frequency, defaulting to 'en'.
    """
    if soup is not None:
        html_tag = soup.find("html")
        if html_tag:
            raw_lang = html_tag.get("lang") or html_tag.get("xml:lang") or ""
            lang_code = raw_lang.strip().split("-")[0].split("_")[0].lower()
            if len(lang_code) == 2 and lang_code.isalpha():
                return lang_code

        meta_lang = soup.find("meta", attrs={"http-equiv": re.compile(r"content-language", re.I)})
        if meta_lang and meta_lang.get("content"):
            lang_code = meta_lang["content"].strip().split("-")[0].split(",")[0].lower()
            if len(lang_code) == 2 and lang_code.isalpha():
                return lang_code

    sample = f" {text_or_html[:4000].lower()} "
    es_hits = sum(sample.count(w) for w in (" de ", " la ", " el ", " los ", " las ", " que ", " por ", " para "))
    en_hits = sum(sample.count(w) for w in (" the ", " and ", " of ", " to ", " in ", " that ", " for ", " with "))

    if es_hits > en_hits and es_hits >= 6:
        return "es"
    return "en"


def _fetch_html_with_encoding(url: str, timeout: float = 20.0) -> Tuple[str, str]:
    """
    Downloads raw HTML from a URL with smart charset detection (e.g., ISO-8859-1 / Windows-1252).
    Returns (html_text, final_url).
    """
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        return downloaded, url

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()

        if not resp.encoding or resp.encoding.lower() == "utf-8":
            soup_pre = BeautifulSoup(resp.content[:4000], "html.parser")
            meta_charset = soup_pre.find("meta", charset=True)
            if meta_charset and meta_charset.get("charset"):
                resp.encoding = meta_charset["charset"]
            else:
                meta_ct = soup_pre.find("meta", attrs={"http-equiv": re.compile(r"content-type", re.I)})
                if meta_ct and "charset=" in meta_ct.get("content", "").lower():
                    resp.encoding = meta_ct["content"].lower().split("charset=")[-1].split(";")[0].strip()

        return resp.text, str(resp.url)


def clean_filename_from_title(title: str, author: Optional[str] = None, max_len: int = 120) -> str:
    """
    Generates a readable PDF filename derived from title and author
    so Zotero displays clean direct item titles in standalone mode.
    """
    title_clean = title.strip() if title else "Article"
    title_clean = re.sub(r'[\\/*?:"<>|]', " - ", title_clean)
    title_clean = re.sub(r"\s+", " ", title_clean).strip(" -_")

    unknown_authors = {
        "unknown",
        "unknown author",
        "not specified",
        "autor desconocido",
        "no especificado",
        "desconocido",
        "none",
        "null",
    }
    author_part = ""
    if author and author.strip() and author.strip().lower() not in unknown_authors:
        auth_clean = re.sub(r'[\\/*?:"<>|]', "", author.strip())
        auth_clean = re.sub(r"\s+", " ", auth_clean).strip(" -_")
        if auth_clean:
            author_part = f" - {auth_clean}"

    full_name = f"{title_clean}{author_part}"
    if len(full_name) > max_len:
        truncated = full_name[:max_len]
        if " " in truncated:
            full_name = truncated.rsplit(" ", 1)[0].strip(" -_")
        else:
            full_name = truncated.strip(" -_")

    if not full_name:
        full_name = "Article"

    candidate = f"{full_name}.pdf"
    target_path = PROCESSED_DIR / candidate
    if not target_path.exists():
        return candidate

    counter = 2
    while (PROCESSED_DIR / f"{full_name} ({counter}).pdf").exists():
        counter += 1
    return f"{full_name} ({counter}).pdf"


def inline_images_as_base64(soup: BeautifulSoup, base_url: str, include_images: bool = True) -> None:
    """
    Downloads referenced images and embeds them directly into the HTML as Base64 Data URIs,
    or removes all image elements when include_images is False.
    """
    if not include_images:
        for tag in soup.find_all(["img", "figure", "picture"]):
            tag.decompose()
        return

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": base_url,
    }

    with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
        for picture in soup.find_all("picture"):
            for source in picture.find_all("source"):
                source.decompose()

        for img in soup.find_all("img"):
            src = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
                or img.get("src")
            )
            if not src:
                img.decompose()
                continue

            if src.startswith("data:image/"):
                continue

            abs_url = urljoin(base_url, src)
            if not abs_url.startswith(("http://", "https://")):
                img.decompose()
                continue

            try:
                resp = client.get(abs_url)
                if resp.status_code == 200 and resp.content:
                    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                    if not content_type.startswith("image/"):
                        ext = Path(urlparse(abs_url).path).suffix.lower()
                        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
                            mime_ext = "svg+xml" if ext == ".svg" else ext.lstrip(".")
                            content_type = f"image/{mime_ext}"
                        else:
                            content_type = "image/jpeg"

                    b64 = base64.b64encode(resp.content).decode("utf-8")
                    img["src"] = f"data:{content_type};base64,{b64}"

                    for attr in ("srcset", "data-src", "data-original", "data-lazy-src", "loading", "sizes"):
                        if img.has_attr(attr):
                            del img[attr]
                else:
                    img.decompose()
            except Exception:
                img.decompose()


def pre_clean_html(html_str: str) -> str:
    """
    Strips social media share widgets, banners, and ads before Trafilatura extraction.
    Ensures content is wrapped in a semantic <article> container so Trafilatura preserves
    headings (h1-h6) on legacy non-HTML5 archive pages.
    """
    if not html_str:
        return ""
    soup_raw = BeautifulSoup(html_str, "html.parser")
    social_patterns = re.compile(
        r"share|social|tweet|twitter|facebook|whatsapp|sharing|sharebox|"
        r"post-share|share-bar|share-buttons|social-icons|newsletter|subscribe|"
        r"author-social|reaction-buttons",
        re.IGNORECASE,
    )
    for tag in soup_raw.find_all(attrs={"class": social_patterns}):
        tag.decompose()
    for tag in soup_raw.find_all(attrs={"id": social_patterns}):
        tag.decompose()
    for a in soup_raw.find_all(
        "a",
        href=re.compile(
            r"twitter\.com/intent/tweet|facebook\.com/sharer|linkedin\.com/share|"
            r"pinterest\.com/pin|api\.whatsapp\.com|t\.me/share|mailto:\?subject",
            re.I,
        ),
    ):
        a.decompose()

    # Legacy HTML pages lacking <article> or <main> cause Trafilatura to fall back to
    # 'recover_wild_text', which strips headings. Wrap body contents to preserve structure.
    if not soup_raw.find(["article", "main"]):
        body = soup_raw.find("body")
        if body:
            art = soup_raw.new_tag("article")
            art.extend(list(body.contents))
            body.append(art)
        else:
            art = soup_raw.new_tag("article")
            art.extend(list(soup_raw.contents))
            soup_raw.append(art)

    return str(soup_raw)


def post_clean_extracted_soup(soup: BeautifulSoup) -> None:
    """Removes unsafe tags and residual share prompts missed by main extraction."""
    for tag in soup.find_all(["script", "style", "iframe", "noscript", "object", "embed"]):
        tag.decompose()

    share_text_pattern = re.compile(
        r"\b(Share\s+Tweet|Tweet\s+Share|Share\s+on\s+Twitter|Share\s+on\s+Facebook|"
        r"Compartir\s+en\s+Twitter|Compartir\s+Tweet)\b",
        re.IGNORECASE,
    )
    for text_node in list(soup.find_all(string=True)):
        if share_text_pattern.search(text_node):
            new_text = share_text_pattern.sub("", text_node)
            text_node.replace_with(new_text)


def clean_and_normalize_headings(soup: BeautifulSoup, doc_title: str = "", doc_author: str = "") -> None:
    """
    Normalizes extracted heading hierarchy:
    1. Promotes standalone bold paragraphs (<p><b>...</b></p>) into <h4> headings.
    2. Removes leading duplicate headings identical to document title or author.
    3. Merges split adjacent numbering/section headings (e.g., <h4>1.</h4> + <h4>TITLE</h4>).
    """
    # 1. Promote short full-bold paragraphs into <h4> headings
    for p in list(soup.find_all("p")):
        bold_child = p.find(["b", "strong"])
        if bold_child and bold_child.parent == p:
            b_text = bold_child.get_text().strip()
            p_text = p.get_text().strip()
            if b_text == p_text and 2 <= len(b_text) <= 120:
                is_num_title = bool(
                    re.match(
                        r"^(\d+\.?|[IVXLCDM]+\.?|Chapter\s+\w+|Section\s+\w+|Part\s+\w+|"
                        r"Cap[íi]tulo\s+\w+|Secci[óo]n\s+\w+|Parte\s+\w+).*$",
                        b_text,
                        re.I,
                    )
                )
                if is_num_title or not b_text.endswith("."):
                    h = soup.new_tag("h4")
                    h.string = b_text
                    p.replace_with(h)

    # 2. Deduplicate leading headings matching main title or author
    norm_title = re.sub(r"\W+", " ", doc_title.lower()).strip() if doc_title else ""
    norm_author = re.sub(r"\W+", " ", doc_author.lower()).strip() if doc_author else ""

    leading_headings = list(soup.find_all(["h1", "h2", "h3"]))[:3]
    for h in leading_headings:
        h_text = re.sub(r"\W+", " ", h.get_text().lower()).strip()
        if (norm_title and (h_text == norm_title or (len(norm_title) > 8 and norm_title in h_text))) or (
            norm_author and (h_text == norm_author or (len(norm_author) > 6 and norm_author in h_text))
        ):
            h.decompose()

    # 3. Merge adjacent numbering/section headings with their subtitles
    headings = list(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]))
    for i in range(len(headings) - 1):
        h1 = headings[i]
        h2 = headings[i + 1]
        if not h1.parent or not h2.parent:
            continue

        is_short_num = bool(re.match(r"^(\d+\.?|[IVXLCDM]+\.?|[A-Za-z]\.?)$", h1.get_text().strip()))
        if h1.name != h2.name and not is_short_num:
            continue

        curr = h1.next_sibling
        is_adjacent = False
        while curr:
            if curr == h2:
                is_adjacent = True
                break
            if getattr(curr, "name", None):
                if curr.get_text(strip=True):
                    break
            curr = curr.next_sibling

        if is_adjacent:
            t1 = h1.get_text().strip()
            t2 = h2.get_text().strip()
            if is_short_num:
                num = t1 if t1.endswith(".") else f"{t1}."
                h2.string = f"{num} {t2}"
                h1.decompose()
            elif h1.name == h2.name and re.match(
                r"^(FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|"
                r"PART\s+\w+|CHAPTER\s+\w+|PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|"
                r"S[ÉE]PTIMA|OCTAVA|NOVENA|D[ÉE]CIMA|PARTE\s+\w+|CAP[ÍI]TULO\s+\w+).*$",
                t1,
                re.I,
            ):
                separator = ": " if not t1.endswith(":") else " "
                h2.string = f"{t1}{separator}{t2}"
                h1.decompose()


def extract_metadata_from_html(raw_html: str, final_url: str) -> Dict[str, Any]:
    """Extracts title, author, date, site name, and language from downloaded HTML."""
    meta = trafilatura.extract_metadata(raw_html)
    title = meta.title if meta and meta.title else ""
    author = meta.author if meta and meta.author else ""
    date = meta.date if meta and meta.date else ""
    sitename = meta.sitename if meta and meta.sitename else urlparse(final_url).netloc

    soup = BeautifulSoup(raw_html, "html.parser")

    # Heuristic for classic archive titles like "Author (Year): Title"
    if not title or not author:
        raw_title_tag = soup.title.string if soup.title and soup.title.string else ""
        if raw_title_tag:
            m = re.match(r"^([^(\n\r]+?)\s*\(\d{4}\):\s*(.+)$", raw_title_tag.strip())
            if m:
                if not author:
                    author = m.group(1).strip()
                if not title:
                    title = m.group(2).strip()

    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else (
            soup.title.string.strip() if soup.title and soup.title.string else ""
        )

    if not author:
        meta_author = soup.find("meta", attrs={"name": re.compile(r"author", re.I)})
        if meta_author and meta_author.get("content"):
            author = meta_author["content"].strip()

    if not author:
        h2 = soup.find("h2")
        if h2 and len(h2.get_text(strip=True)) < 50:
            author = h2.get_text(strip=True)

    language = detect_document_language(soup.get_text(" ", strip=True), soup=soup)
    fallback_title = urlparse(final_url).path.split("/")[-1] or "Web Article"

    return {
        "title": title.strip() if title else fallback_title,
        "author": author.strip() if author and author.lower() not in ("none", "null") else "",
        "date": date.strip() if date else "",
        "sitename": sitename.strip() if sitename else urlparse(final_url).netloc,
        "url": final_url,
        "language": language,
    }


def extract_article_content(url: str, include_images: bool = True) -> Dict[str, Any]:
    """
    Downloads and extracts clean structured article content using Trafilatura
    with BeautifulSoup fallback, heading normalization, and inline Base64 images.
    """
    downloaded, final_url = _fetch_html_with_encoding(url, timeout=20.0)
    meta_info = extract_metadata_from_html(downloaded, final_url)

    title = meta_info["title"]
    author = meta_info["author"]
    date = meta_info["date"]
    sitename = meta_info["sitename"]
    language = meta_info["language"]

    cleaned_downloaded = pre_clean_html(downloaded)

    raw_soup = BeautifulSoup(cleaned_downloaded, "html.parser")
    raw_headings_count = len(raw_soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]))

    extracted_html = trafilatura.extract(
        cleaned_downloaded,
        output_format="html",
        include_formatting=True,
        include_images=include_images,
        include_links=True,
    )

    ext_soup = BeautifulSoup(extracted_html or "", "html.parser")
    ext_headings_count = len(ext_soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]))

    # Fallback if Trafilatura fails, yields tiny output, or drops headings present in original
    if not extracted_html or len(extracted_html.strip()) < 100 or (raw_headings_count > 0 and ext_headings_count == 0):
        soup = BeautifulSoup(cleaned_downloaded, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside", "header", "iframe", "noscript"]):
            tag.decompose()

        article_node = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_=re.compile(r"content|post|entry|article", re.I))
        )
        if article_node:
            extracted_html = str(article_node)
        else:
            body = soup.find("body")
            extracted_html = str(body) if body else str(soup)

    soup = BeautifulSoup(extracted_html or "<p>No content could be extracted.</p>", "html.parser")
    post_clean_extracted_soup(soup)
    clean_and_normalize_headings(soup, doc_title=title, doc_author=author)
    inline_images_as_base64(soup, final_url, include_images=include_images)

    return {
        "title": title,
        "author": author if author else "Not specified",
        "date": date,
        "sitename": sitename,
        "url": final_url,
        "language": language,
        "html_body": str(soup),
    }


def build_reader_html_document(
    article: Dict[str, Any],
    style: str = "academic",
    zotero_mode: str = "standalone",
) -> str:
    """Builds a print-ready reader HTML document formatted for Zotero reading and highlighting."""
    if style == "sans":
        font_family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    else:
        font_family = "'Charter', 'Sitka Text', 'Cambria', Georgia, serif"

    raw_title = article["title"]
    raw_author = article.get("author", "")
    raw_date = article.get("date", "")
    raw_url = article["url"]
    lang = article.get("language", "en")
    body = article["html_body"]

    safe_title = html_escape(raw_title, quote=True)
    safe_author = html_escape(raw_author, quote=True)
    safe_date = html_escape(raw_date, quote=True)
    safe_url = html_escape(raw_url, quote=True)
    safe_lang = html_escape(lang if len(lang) == 2 else "en", quote=True)

    date_html = f"<span><strong>Date:</strong> {safe_date}</span>" if raw_date else ""
    author_html = (
        f"<span><strong>Author:</strong> {safe_author}</span>"
        if raw_author and raw_author.lower() not in ("not specified", "no especificado", "unknown")
        else ""
    )
    html_title = "" if zotero_mode == "standalone" else safe_title

    return f"""<!DOCTYPE html>
<html lang="{safe_lang}">
<head>
<meta charset="utf-8">
<title>{html_title}</title>
<style>
@page {{
    size: A4;
    margin: 22mm 18mm 22mm 18mm;
    @bottom-right {{
        content: counter(page);
    }}
}}
* {{
    box-sizing: border-box;
}}
body {{
    font-family: {font_family};
    font-size: 10.5pt;
    line-height: 1.65;
    color: #1e293b;
    max-width: 820px;
    margin: 0 auto;
    background: #ffffff;
}}
.article-header {{
    margin-bottom: 2.2rem;
    padding-bottom: 1.25rem;
    border-bottom: 1.5px solid #cbd5e1;
}}
.article-title {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 23pt;
    font-weight: 700;
    line-height: 1.25;
    margin-bottom: 0.85rem;
    color: #0f172a;
    letter-spacing: -0.02em;
}}
.article-meta {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 9pt;
    color: #64748b;
    display: flex;
    flex-wrap: wrap;
    gap: 1.25rem;
    align-items: center;
}}
.article-meta a {{
    color: #2563eb;
    text-decoration: none;
    word-break: break-all;
}}
h2, h3, h4, h5 {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #0f172a;
    page-break-after: avoid;
    break-after: avoid;
    margin-top: 1.8em;
    margin-bottom: 0.55em;
}}
h2 {{ font-size: 15pt; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.3rem; }}
h3 {{ font-size: 12.5pt; }}
h4 {{ font-size: 11pt; }}
p {{
    margin-bottom: 1.15em;
    text-align: justify;
    text-justify: inter-word;
    orphans: 3;
    widows: 3;
}}
blockquote {{
    border-left: 3.5px solid #94a3b8;
    margin: 1.4em 0;
    padding: 0.5em 1.2em;
    color: #334155;
    background-color: #f8fafc;
    font-style: italic;
}}
pre, code {{
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 9pt;
    background-color: #f1f5f9;
    border-radius: 3px;
}}
pre {{
    padding: 1rem;
    overflow-x: auto;
    border: 1px solid #e2e8f0;
    margin: 1.2em 0;
    white-space: pre-wrap;
    word-wrap: break-word;
}}
code {{
    padding: 0.15em 0.35em;
}}
img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1.6em auto;
    border-radius: 4px;
    page-break-inside: avoid;
    break-inside: avoid;
}}
figure {{
    margin: 1.8em 0;
    text-align: center;
    page-break-inside: avoid;
    break-inside: avoid;
}}
figcaption {{
    font-size: 8.5pt;
    color: #64748b;
    margin-top: 0.45em;
    font-style: italic;
    text-align: center;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1.5em 0;
    font-size: 9.5pt;
}}
th, td {{
    border: 1px solid #cbd5e1;
    padding: 0.5rem 0.75rem;
    text-align: left;
}}
th {{
    background-color: #f1f5f9;
    font-weight: 600;
}}
ul, ol {{
    margin-bottom: 1.2em;
    padding-left: 1.8em;
}}
li {{
    margin-bottom: 0.4em;
}}
</style>
</head>
<body>
<header class="article-header">
    <h1 class="article-title">{safe_title}</h1>
    <div class="article-meta">
        {author_html}
        {date_html}
        <span><strong>Source:</strong> <a href="{safe_url}">{safe_url}</a></span>
    </div>
</header>
<main class="article-content">
{body}
</main>
</body>
</html>"""


def fetch_web_metadata(url: str) -> Dict[str, Any]:
    """
    Quickly extracts title, author, date, and site name from a URL
    so users can preview and edit metadata before generating the PDF.
    """
    downloaded, final_url = _fetch_html_with_encoding(url, timeout=15.0)
    return extract_metadata_from_html(downloaded, final_url)


def convert_web_to_pdf(
    url: str,
    mode: str = "reader",
    style: str = "academic",
    include_images: bool = True,
    custom_title: Optional[str] = None,
    custom_author: Optional[str] = None,
    custom_date: Optional[str] = None,
    zotero_mode: str = "standalone",
) -> Dict[str, Any]:
    """
    Converts a web URL into a PDF with optional metadata overrides.
    - zotero_mode='standalone': Clears internal PDF metadata and uses a descriptive filename so
      Zotero imports it directly as a top-level PDF without nested container items.
    - zotero_mode='parent': Embeds full metadata for bibliographic container item creation.
    - mode='reader': Extracts clean article content and embeds images as Base64.
    - mode='fullpage': Renders the full live page preserving original CSS styling.
    """
    browser_bin = find_browser_binary()

    temp_html_path: Optional[str] = None
    raw_pdf_path: Optional[Path] = None
    target_to_render = url
    article_info: Dict[str, Any] = {
        "title": "Web Page",
        "author": "Not specified",
        "date": "",
        "url": url,
        "language": "en",
    }

    try:
        if mode == "reader":
            article_info = extract_article_content(url, include_images=include_images)

            if custom_title and custom_title.strip():
                article_info["title"] = custom_title.strip()
            if custom_author and custom_author.strip():
                article_info["author"] = custom_author.strip()
            if custom_date and custom_date.strip():
                article_info["date"] = custom_date.strip()

            rendered_html = build_reader_html_document(article_info, style=style, zotero_mode=zotero_mode)

            tmp_fd, temp_html_path = tempfile.mkstemp(suffix=".html", prefix="reader_")
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(rendered_html)
            target_to_render = f"file://{temp_html_path}"
        else:
            default_title = urlparse(url).path.split("/")[-1] or urlparse(url).netloc
            article_info["title"] = (
                custom_title.strip() if custom_title and custom_title.strip() else default_title
            )
            if custom_author and custom_author.strip():
                article_info["author"] = custom_author.strip()
            if custom_date and custom_date.strip():
                article_info["date"] = custom_date.strip()

        output_filename = clean_filename_from_title(article_info["title"], article_info.get("author"))
        final_pdf_path = PROCESSED_DIR / output_filename
        raw_pdf_path = PROCESSED_DIR / f"raw_{output_filename}"

        cmd = [
            browser_bin,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--run-all-compositor-stages-before-draw",
        ]
        if mode == "fullpage":
            cmd.append("--virtual-time-budget=6000")
        cmd.extend([
            f"--print-to-pdf={str(raw_pdf_path)}",
            target_to_render,
        ])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Headless browser timed out while rendering the webpage to PDF.") from exc

        if proc.returncode != 0 or not raw_pdf_path.exists() or raw_pdf_path.stat().st_size == 0:
            raise RuntimeError(f"Browser failed to generate PDF: {proc.stderr[:300]}")

        doc = pymupdf.open(str(raw_pdf_path))
        try:
            page_count = len(doc)
            if zotero_mode == "standalone":
                # Strip internal metadata so Zotero does not wrap it inside a parent item
                doc.set_metadata({
                    "title": "",
                    "author": "",
                    "subject": "",
                    "keywords": "",
                    "creator": "",
                })
            else:
                doc.set_metadata({
                    "title": article_info["title"],
                    "author": article_info.get("author", ""),
                    "subject": f"Web article extracted from {url}",
                    "keywords": f"Zotero, Web Article, {url}",
                    "creator": "PDF Toolbox / Zotero Web Converter",
                })
            doc.save(str(final_pdf_path), garbage=4, deflate=True)
        finally:
            doc.close()

        final_size = final_pdf_path.stat().st_size

        return {
            "success": True,
            "filename": output_filename,
            "filepath": str(final_pdf_path),
            "title": article_info["title"],
            "author": article_info.get("author", "Not specified"),
            "date": article_info.get("date", ""),
            "source_url": url,
            "pages": page_count,
            "filesize_bytes": final_size,
            "filesize_formatted": format_bytes(final_size),
            "mode": mode,
            "zotero_mode": zotero_mode,
        }

    finally:
        if raw_pdf_path and raw_pdf_path.exists():
            raw_pdf_path.unlink(missing_ok=True)
        if temp_html_path and os.path.exists(temp_html_path):
            try:
                os.remove(temp_html_path)
            except OSError:
                pass
