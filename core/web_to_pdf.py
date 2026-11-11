import os
import re
import shutil
import subprocess
import tempfile
import uuid
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
import pymupdf
import trafilatura
from bs4 import BeautifulSoup

from .utils import format_bytes, PROCESSED_DIR


def find_browser_binary() -> str:
    """Busca el ejecutable de Chromium / Helium / Chrome en el sistema."""
    candidates = [
        "/usr/bin/helium-browser",
        "/opt/helium-browser-bin/chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("helium-browser"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise RuntimeError(
        "No se encontró un navegador basado en Chromium (Helium, Chrome, Chromium) para la conversión."
    )


def clean_filename_from_title(title: str, author: Optional[str] = None, max_len: int = 120) -> str:
    """
    Genera un nombre de archivo limpio, amigable y legible para el PDF,
    ideal para que en Zotero aparezca con título y autor correctos como ítem directo.
    """
    title_clean = title.strip() if title else "Articulo"
    # Reemplazar caracteres no permitidos en sistemas de archivos
    title_clean = re.sub(r'[\\/*?:"<>|]', " - ", title_clean)
    title_clean = re.sub(r"\s+", " ", title_clean).strip(" -_")

    author_part = ""
    if author and author.strip() and author.lower() not in ("autor desconocido", "no especificado", "desconocido", "none"):
        auth_clean = re.sub(r'[\\/*?:"<>|]', "", author.strip())
        auth_clean = re.sub(r"\s+", " ", auth_clean).strip(" -_")
        if auth_clean:
            author_part = f" - {auth_clean}"

    full_name = f"{title_clean}{author_part}"
    if len(full_name) > max_len:
        # Truncar limpiamente respetando palabras
        truncated = full_name[:max_len]
        if " " in truncated:
            full_name = truncated.rsplit(" ", 1)[0].strip(" -_")
        else:
            full_name = truncated.strip(" -_")

    if not full_name:
        full_name = "Articulo"

    candidate = f"{full_name}.pdf"
    target_path = PROCESSED_DIR / candidate
    if not target_path.exists():
        return candidate

    counter = 2
    while (PROCESSED_DIR / f"{full_name} ({counter}).pdf").exists():
        counter += 1
    return f"{full_name} ({counter}).pdf"


def inline_images_as_base64(soup: BeautifulSoup, base_url: str, include_images: bool = True):
    """
    Si include_images es False, remueve todas las imágenes y figuras.
    Si es True, descarga cada imagen y la incrusta directamente en el HTML como base64 Data URI.
    Esto garantiza que el motor Chromium las guarde dentro del PDF sin problemas de CORS ni tiempos de espera.
    """
    if not include_images:
        for tag in soup.find_all(["img", "figure", "picture"]):
            tag.decompose()
        return

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": base_url,
    }

    with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
        # Procesar fuentes en <picture>
        for picture in soup.find_all("picture"):
            # Dejar que el tag <img> interno maneje la fuente principal
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

            # Si ya está incrustada
            if src.startswith("data:image/"):
                continue

            abs_url = urljoin(base_url, src)
            try:
                resp = client.get(abs_url)
                if resp.status_code == 200 and resp.content:
                    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                    if not content_type.startswith("image/"):
                        # Intentar deducir extensión
                        ext = Path(urlparse(abs_url).path).suffix.lower()
                        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
                            content_type = f"image/{ext.lstrip('.')}"
                        else:
                            content_type = "image/jpeg"
                    
                    b64 = base64.b64encode(resp.content).decode("utf-8")
                    img["src"] = f"data:{content_type};base64,{b64}"
                    
                    # Eliminar atributos que puedan interferir con lazy load
                    for attr in ["srcset", "data-src", "data-original", "data-lazy-src", "loading", "sizes"]:
                        if img.has_attr(attr):
                            del img[attr]
                else:
                    img.decompose()
            except Exception:
                img.decompose()


def pre_clean_html(html_str: str) -> str:
    """
    Elimina bloques de redes sociales, botones de compartir (Share, Tweet, etc.),
    anuncios y elementos secundarios antes de la extracción de trafilatura.
    Asimismo, asegura que el documento tenga un contenedor semántico <article>
    para que trafilatura no descarte los encabezados (h1-h6) en páginas web clásicas.
    """
    if not html_str:
        return ""
    soup_raw = BeautifulSoup(html_str, "html.parser")
    social_patterns = re.compile(
        r"share|social|tweet|twitter|facebook|whatsapp|sharing|sharebox|"
        r"post-share|share-bar|share-buttons|social-icons|newsletter|subscribe|"
        r"author-social|reaction-buttons",
        re.IGNORECASE
    )
    for tag in soup_raw.find_all(attrs={"class": social_patterns}):
        tag.decompose()
    for tag in soup_raw.find_all(attrs={"id": social_patterns}):
        tag.decompose()
    for a in soup_raw.find_all("a", href=re.compile(r"twitter\.com/intent/tweet|facebook\.com/sharer|linkedin\.com/share|pinterest\.com/pin|api\.whatsapp\.com|t\.me/share|mailto:\?subject", re.I)):
        a.decompose()

    # Si la página web no tiene un contenedor semántico <article> o <main>
    # (muy común en páginas web clásicas y archivos históricos como marxists.org),
    # trafilatura cae en 'recover_wild_text', el cual descarta todos los encabezados <h1>-<h6>.
    # Envolver el contenido del body en un <article> preserva todos los títulos y subtítulos.
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


def post_clean_extracted_soup(soup: BeautifulSoup):
    """
    Limpia cualquier texto residual de compartir (Share, Tweet, etc.) que trafilatura haya incluido en el contenido.
    """
    share_text_pattern = re.compile(
        r"\b(Share\s+Tweet|Tweet\s+Share|Share\s+on\s+Twitter|Compartir\s+en\s+Twitter|Compartir\s+Tweet)\b",
        re.IGNORECASE
    )
    for text_node in list(soup.find_all(string=True)):
        if share_text_pattern.search(text_node):
            new_text = share_text_pattern.sub("", text_node)
            text_node.replace_with(new_text)


def clean_and_normalize_headings(soup: BeautifulSoup, doc_title: str = "", doc_author: str = ""):
    """
    Mejora y estructura la jerarquía de títulos y subtítulos del documento:
    1. Promueve párrafos destacados en negrita (<p><b>Subtítulo</b></p>) a encabezados <h4> reales.
    2. Elimina títulos iniciales duplicados que repiten redundantemente el título o autor del artículo.
    3. Fusiona encabezados adyacentes de numeración/sección (ej. <h4>1.</h4> seguido de <h4>TITULO</h4> -> <h4>1. TITULO</h4>,
       o <h3>PRIMERA PARTE</h3> seguido de <h3>TITULO PARTE</h3> -> <h3>PRIMERA PARTE: TITULO PARTE</h3>).
    """
    # 1. Promover párrafos breves que son 100% negrita a encabezados h4
    for p in list(soup.find_all("p")):
        bold_child = p.find(["b", "strong"])
        if bold_child and bold_child.parent == p:
            b_text = bold_child.get_text().strip()
            p_text = p.get_text().strip()
            if b_text == p_text and len(b_text) >= 2 and len(b_text) <= 120:
                is_num_title = bool(re.match(r"^(\d+\.?|[IVXLCDM]+\.?|Cap[íi]tulo\s+\w+|Secci[óo]n\s+\w+|Parte\s+\w+).*$", b_text, re.I))
                if is_num_title or not b_text.endswith("."):
                    h = soup.new_tag("h4")
                    h.string = b_text
                    p.replace_with(h)

    # 2. Desduplicar encabezados iniciales que repitan el título o autor general
    norm_title = re.sub(r"\W+", " ", doc_title.lower()).strip() if doc_title else ""
    norm_author = re.sub(r"\W+", " ", doc_author.lower()).strip() if doc_author else ""

    leading_headings = list(soup.find_all(["h1", "h2", "h3"]))[:3]
    for h in leading_headings:
        h_text = re.sub(r"\W+", " ", h.get_text().lower()).strip()
        if (norm_title and (h_text == norm_title or (len(norm_title) > 8 and norm_title in h_text))) or \
           (norm_author and (h_text == norm_author or (len(norm_author) > 6 and norm_author in h_text))):
            h.decompose()

    # 3. Fusionar encabezados adyacentes de numeración / sección con su subtítulo
    headings = list(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]))
    for i in range(len(headings) - 1):
        h1 = headings[i]
        h2 = headings[i+1]
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
            elif h1.name == h2.name and re.match(r"^(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|S[ÉE]PTIMA|OCTAVA|NOVENA|D[ÉE]CIMA|PARTE\s+\w+|CAP[ÍI]TULO\s+\w+).*$", t1, re.I):
                separator = ": " if not t1.endswith(":") else " "
                h2.string = f"{t1}{separator}{t2}"
                h1.decompose()


def extract_article_content(url: str, include_images: bool = True) -> Dict[str, Any]:
    """
    Descarga y extrae el contenido estructurado del artículo utilizando trafilatura
    con fallback a BeautifulSoup, limpiando botones de redes sociales, garantizando
    la preservación de títulos y subtítulos e incrustando imágenes en base64.
    """
    downloaded = trafilatura.fetch_url(url)
    
    if not downloaded:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=20.0)
        resp.raise_for_status()
        
        # Detección inteligente de codificación para páginas clásicas (ISO-8859-1, Windows-1252)
        if not resp.encoding or resp.encoding.lower() == "utf-8":
            soup_pre = BeautifulSoup(resp.content[:4000], "html.parser")
            meta_charset = soup_pre.find("meta", charset=True)
            if meta_charset:
                resp.encoding = meta_charset["charset"]
            else:
                meta_ct = soup_pre.find("meta", attrs={"http-equiv": re.compile(r"content-type", re.I)})
                if meta_ct and "charset=" in meta_ct.get("content", "").lower():
                    resp.encoding = meta_ct["content"].lower().split("charset=")[-1].split(";")[0].strip()
        downloaded = resp.text

    # Metadatos
    meta = trafilatura.extract_metadata(downloaded)
    title = meta.title if meta and meta.title else ""
    author = meta.author if meta and meta.author else ""
    date = meta.date if meta and meta.date else ""
    sitename = meta.sitename if meta and meta.sitename else urlparse(url).netloc

    # Heurística para títulos de archivos clásicos como "Autor (Año): Título"
    if not title or not author:
        soup_meta = BeautifulSoup(downloaded, "html.parser")
        raw_title_tag = soup_meta.title.string if soup_meta.title else ""
        if raw_title_tag:
            m = re.match(r"^([^(\n\r]+?)\s*\(\d{4}\):\s*(.+)$", raw_title_tag.strip())
            if m:
                if not author:
                    author = m.group(1).strip()
                if not title:
                    title = m.group(2).strip()

    # Limpiar previamente el HTML para remover botones 'Share', 'Tweet', widgets sociales
    # y asegurar envoltura <article> para no perder títulos ni subtítulos
    cleaned_downloaded = pre_clean_html(downloaded)

    # Verificar encabezados en el original para asegurar que trafilatura no los descarte
    raw_soup = BeautifulSoup(cleaned_downloaded, "html.parser")
    raw_headings_count = len(raw_soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]))

    # Extracción de contenido principal con imágenes
    extracted_html = trafilatura.extract(
        cleaned_downloaded,
        output_format="html",
        include_formatting=True,
        include_images=include_images,
        include_links=True
    )

    ext_soup = BeautifulSoup(extracted_html or "", "html.parser")
    ext_headings_count = len(ext_soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]))

    # Si trafilatura falló, el texto es ínfimo o descartó los encabezados existiendo en el original:
    if not extracted_html or len(extracted_html.strip()) < 100 or (raw_headings_count > 0 and ext_headings_count == 0):
        soup = BeautifulSoup(cleaned_downloaded, "html.parser")
        
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else (soup.title.string if soup.title else "Artículo")

        for tag in soup(["script", "style", "nav", "footer", "aside", "header", "iframe", "noscript"]):
            tag.decompose()

        article_node = soup.find("article") or soup.find("main") or soup.find(class_=re.compile(r"content|post|entry|article", re.I))
        if article_node:
            extracted_html = str(article_node)
        else:
            body = soup.find("body")
            extracted_html = str(body) if body else str(soup)

    if not title:
        title = urlparse(url).path.split("/")[-1] or "Artículo Web"

    # Procesar, post-limpiar, normalizar títulos y subtítulos e incrustar imágenes
    soup = BeautifulSoup(extracted_html or "", "html.parser")
    post_clean_extracted_soup(soup)
    clean_and_normalize_headings(soup, doc_title=title, doc_author=author)
    inline_images_as_base64(soup, url, include_images=include_images)

    return {
        "title": title.strip(),
        "author": author.strip() if author and author.lower() != "none" else "No especificado",
        "date": date.strip() if date else "",
        "sitename": sitename,
        "url": url,
        "html_body": str(soup)
    }


def build_reader_html_document(article: Dict[str, Any], style: str = "academic", zotero_mode: str = "standalone") -> str:
    """
    Construye un documento HTML estilizado especialmente para lectura y remarcado en Zotero.
    """
    if style == "sans":
        font_family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    else:
        font_family = "'Charter', 'Sitka Text', 'Cambria', Georgia, serif"

    title = article["title"]
    author = article["author"]
    date = article["date"]
    url = article["url"]
    body = article["html_body"]

    date_html = f"<span><strong>Fecha:</strong> {date}</span>" if date else ""
    author_html = f"<span><strong>Autor:</strong> {author}</span>" if author and author != "No especificado" else ""
    html_title = "" if zotero_mode == "standalone" else title

    return f"""<!DOCTYPE html>
<html lang="es">
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
    <h1 class="article-title">{title}</h1>
    <div class="article-meta">
        {author_html}
        {date_html}
        <span><strong>Fuente:</strong> <a href="{url}">{url}</a></span>
    </div>
</header>
<main class="article-content">
{body}
</main>
</body>
</html>"""


def fetch_web_metadata(url: str) -> Dict[str, Any]:
    """
    Extrae rápidamente título, autor, fecha y sitio web de una URL
    para permitir al usuario previsualizar y editar antes de generar el PDF.
    """
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=15.0)
        resp.raise_for_status()
        if not resp.encoding or resp.encoding.lower() == "utf-8":
            soup_pre = BeautifulSoup(resp.content[:4000], "html.parser")
            meta_charset = soup_pre.find("meta", charset=True)
            if meta_charset:
                resp.encoding = meta_charset["charset"]
            else:
                meta_ct = soup_pre.find("meta", attrs={"http-equiv": re.compile(r"content-type", re.I)})
                if meta_ct and "charset=" in meta_ct.get("content", "").lower():
                    resp.encoding = meta_ct["content"].lower().split("charset=")[-1].split(";")[0].strip()
        downloaded = resp.text

    meta = trafilatura.extract_metadata(downloaded)
    title = meta.title if meta and meta.title else ""
    author = meta.author if meta and meta.author else ""
    date = meta.date if meta and meta.date else ""
    sitename = meta.sitename if meta and meta.sitename else urlparse(url).netloc

    soup = BeautifulSoup(downloaded, "html.parser")
    # Heurística para títulos de archivos clásicos como "Autor (Año): Título"
    if not title or not author:
        raw_title_tag = soup.title.string if soup.title else ""
        if raw_title_tag:
            m = re.match(r"^([^(\n\r]+?)\s*\(\d{4}\):\s*(.+)$", raw_title_tag.strip())
            if m:
                if not author:
                    author = m.group(1).strip()
                if not title:
                    title = m.group(2).strip()

    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else (soup.title.string if soup.title else "")

    if not author:
        h2 = soup.find("h2")
        if h2 and len(h2.get_text(strip=True)) < 50:
            author = h2.get_text(strip=True)

    return {
        "title": title.strip() if title else urlparse(url).path.split("/")[-1] or "Artículo Web",
        "author": author.strip() if author and author.lower() != "none" else "",
        "date": date.strip() if date else "",
        "sitename": sitename,
        "url": url
    }


def convert_web_to_pdf(
    url: str,
    mode: str = "reader",
    style: str = "academic",
    include_images: bool = True,
    custom_title: Optional[str] = None,
    custom_author: Optional[str] = None,
    custom_date: Optional[str] = None,
    zotero_mode: str = "standalone"
) -> Dict[str, Any]:
    """
    Convierte una URL a PDF permitiendo sobreescribir metadatos (autor, título, fecha).
    zotero_mode='standalone': Genera el PDF con metadatos limpios y nombre descriptivo para que
                             en Zotero aparezca como un archivo directo sin subcarpetas ni subarchivos 'PDF'.
    zotero_mode='parent': Incrusta metadatos completos para que Zotero cree una ficha bibliográfica.
    mode='reader': Extrae el artículo limpio e incrusta imágenes en base64 (recomendado para Zotero).
    mode='fullpage': Renderiza la página web completa esperando la carga de assets.
    """
    browser_bin = find_browser_binary()

    temp_html_path = None
    target_to_render = url
    article_info = {
        "title": "Página Web",
        "author": "Desconocido",
        "date": "",
        "url": url
    }

    try:
        if mode == "reader":
            article_info = extract_article_content(url, include_images=include_images)
            
            # Aplicar metadatos personalizados si fueron definidos por el usuario
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
            article_info["title"] = custom_title.strip() if custom_title and custom_title.strip() else default_title
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
            f"--print-to-pdf={str(raw_pdf_path)}",
        ]

        if mode == "fullpage":
            cmd.insert(4, "--virtual-time-budget=6000")

        cmd.append(target_to_render)
        
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0 or not raw_pdf_path.exists() or raw_pdf_path.stat().st_size == 0:
            raise RuntimeError(f"Fallo al generar PDF con el navegador: {proc.stderr[:300]}")

        # Configuración de metadatos según el modo Zotero
        doc = pymupdf.open(str(raw_pdf_path))
        page_count = len(doc)
        if zotero_mode == "standalone":
            # Modo Standalone: Limpia los metadatos internos para que Zotero
            # no interprete el archivo como una revista académica y cree una carpeta 'Parent Item'
            # con un subarchivo llamado 'PDF'.
            # De esta forma Zotero lo importa directamente como un archivo PDF de primer nivel.
            doc.set_metadata({
                "title": "",
                "author": "",
                "subject": "",
                "keywords": "",
                "creator": ""
            })
        else:
            # Modo Ficha Bibliográfica: Incrusta los metadatos completos
            doc.set_metadata({
                "title": article_info["title"],
                "author": article_info.get("author", ""),
                "subject": f"Artículo web extraído de {url}",
                "keywords": f"Zotero, Web Article, {url}",
                "creator": "PDF Toolbox / Zotero Web Converter"
            })
        doc.save(str(final_pdf_path), garbage=4, deflate=True)
        doc.close()

        if raw_pdf_path.exists():
            raw_pdf_path.unlink(missing_ok=True)

        final_size = final_pdf_path.stat().st_size

        return {
            "success": True,
            "filename": output_filename,
            "filepath": str(final_pdf_path),
            "title": article_info["title"],
            "author": article_info.get("author", "No especificado"),
            "date": article_info.get("date", ""),
            "source_url": url,
            "pages": page_count,
            "filesize_bytes": final_size,
            "filesize_formatted": format_bytes(final_size),
            "mode": mode,
            "zotero_mode": zotero_mode,
        }

    finally:
        if temp_html_path and os.path.exists(temp_html_path):
            try:
                os.remove(temp_html_path)
            except Exception:
                pass
