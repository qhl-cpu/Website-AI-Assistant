"""Read and prepare one explicitly selected webpage or file."""

import json
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from zipfile import ZipFile

import httpx
from bs4 import BeautifulSoup
from docx import Document
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from app.knowledge.chunking import (
    build_chunk,
    chunk_document,
    count_tokens,
    get_encoding,
    split_long_text_by_tokens,
)
from app.knowledge.cleaning import clean_document
from app.knowledge.wordpress import build_document, detect_page_type, html_to_text


PAGE_HOSTS = {"www.vancouverlaser.com", "vancouverlaser.com"}
WORDPRESS_TYPES = {"pages", "treatment", "concern", "posts"}
WORDPRESS_ITEM = re.compile(r"/wp-json/wp/v2/(pages|treatment|concern|posts)/([1-9][0-9]*)/?")
MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 600_000
MAX_CHUNKS = 500


class ContentError(ValueError):
    """Content could not be fetched or converted into searchable text."""


def page_url(value: str) -> str:
    """Only accept HTTPS pages on the clinic's own hosts."""
    if len(value) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", value.strip()):
        raise ContentError("Enter a valid Vancouver Laser webpage URL.")
    try:
        parts = urlsplit(value.strip())
        host = parts.hostname
        if parts.scheme != "https" or host not in PAGE_HOSTS or parts.netloc.lower() != host:
            raise ValueError
    except ValueError as error:
        raise ContentError("Enter an HTTPS URL on vancouverlaser.com.") from error
    return urlunsplit(("https", host, parts.path or "/", "", ""))


def page_key(url: str) -> str:
    """Use one identity for www, trailing slashes and tracking parameters."""
    return urlsplit(page_url(url)).path.rstrip("/") or "/"


def download(client: httpx.Client, url: str, *, json_response: bool = False) -> tuple[bytes, str]:
    # Validate each redirect before sending any request, and cap decoded body size.
    for _ in range(5):
        with client.stream("GET", url) as response:
            if response.is_redirect:
                target = page_url(urljoin(url, response.headers.get("location", "")))
                if json_response and not WORDPRESS_ITEM.fullmatch(urlsplit(target).path):
                    raise ContentError("WordPress did not return the requested page record.")
                url = target
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if json_response and "json" not in content_type:
                raise ContentError("WordPress did not return a page record.")
            if not json_response and "text/html" not in content_type:
                raise ContentError("The URL did not return an HTML webpage.")
            body = bytearray()
            for part in response.iter_bytes():
                body.extend(part)
                if len(body) > MAX_DOWNLOAD_BYTES:
                    raise ContentError("The webpage is too large to index.")
            return bytes(body), url
    raise ContentError("The webpage redirects too many times.")


def read_wordpress(client: httpx.Client, url: str, post_type: str, wp_id: int) -> dict:
    host = urlsplit(url).netloc
    body, _ = download(
        client, f"https://{host}/wp-json/wp/v2/{post_type}/{wp_id}", json_response=True
    )
    item = json.loads(body)
    if item.get("id") != wp_id or item.get("status") != "publish":
        raise ContentError("WordPress did not return the requested published page.")
    if item.get("content", {}).get("protected"):
        raise ContentError("Password protected webpages cannot be indexed.")
    document = build_document(item, post_type)
    document["url"] = page_url(document["url"])
    return document


def read_page(url: str, *, wp_id: int | None = None, post_type: str | None = None) -> dict:
    url = page_url(url)
    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            if wp_id and post_type in WORDPRESS_TYPES:
                return read_wordpress(client, url, post_type, wp_id)

            body, final_url = download(client, url)
            soup = BeautifulSoup(body, "html.parser")
            for link in soup.select('link[rel="alternate"][type="application/json"][href]'):
                discovered = urlsplit(urljoin(final_url, link["href"]))
                match = WORDPRESS_ITEM.fullmatch(discovered.path)
                if match and discovered.hostname in PAGE_HOSTS:
                    return read_wordpress(client, final_url, match[1], int(match[2]))

            if soup.select_one('form.post-password-form, form[action*="postpass"]'):
                raise ContentError("Password protected webpages cannot be indexed.")
            main = (
                soup.select_one("main, [role=main], #main")
                or soup.select_one('[data-elementor-type="wp-page"], [data-elementor-type="single-post"]')
                or soup.find("article")
            )
            if not main:
                raise ContentError("Could not find the main content of this webpage.")
            heading = main.find("h1") or soup.title
            return {
                "wp_id": None,
                "doc_id": None,
                "title": heading.get_text(" ", strip=True) if heading else final_url,
                "url": final_url,
                "status": "publish",
                "post_type": "pages",
                "page_type": detect_page_type(final_url, post_type="pages"),
                "source": "website_html",
                "content": html_to_text(str(main)),
            }
    except (httpx.HTTPError, ValueError, AttributeError, TypeError) as error:
        if isinstance(error, ContentError):
            raise
        raise ContentError("Could not read this public webpage. Check the URL and try again.") from error


def read_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted or len(reader.pages) > 200:
        raise ContentError("Upload an unencrypted PDF with 200 pages or fewer.")
    parts = [page.extract_text() or "" for page in reader.pages]
    if not any(part.strip() for part in parts):
        raise ContentError("This PDF has no selectable text. Run OCR before uploading it.")
    return "\n\n".join(parts)


def read_docx(data: bytes) -> str:
    with ZipFile(BytesIO(data)) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > 40 * 1024 * 1024:
            raise ContentError("This Word document is too large to extract.")
    document = Document(BytesIO(data))
    lines = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            lines.append(block.text)
        else:
            lines.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
    return "\n\n".join(lines)


def read_file(filename: str, data: bytes) -> dict:
    filename = Path(filename.replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ContentError("Files must be 10 MB or smaller.")
    try:
        if suffix == ".pdf":
            content = read_pdf(data)
        elif suffix == ".docx":
            content = read_docx(data)
        elif suffix in {".txt", ".md", ".markdown"}:
            content = data.decode("utf-8-sig")
        else:
            raise ContentError("Choose a PDF, DOCX, UTF-8 TXT, or Markdown file.")
    except ContentError:
        raise
    except Exception as error:
        raise ContentError("Could not extract text from this file. Check the format and try again.") from error
    if not content.strip():
        raise ContentError("The file contains no readable text.")
    return {
        "title": filename[:250],
        "content": content,
        "url": "",
        "status": "manual",
        "post_type": "manual",
        "page_type": "document",
        "source": "uploaded_file",
    }


def prepare_chunks(document: dict) -> list[dict]:
    """Split one source, keeping the website's existing section rules."""
    content = document["content"].strip()
    if len(content) > MAX_TEXT_CHARS:
        raise ContentError("This source contains too much text to index in one operation.")
    encoding = get_encoding()
    if document["source"] != "uploaded_file":
        document = clean_document(document)
        chunks = chunk_document(document, encoding)
    else:
        chunks = [
            build_chunk(document, text, index, "general", count_tokens(text, encoding))
            for index, text in enumerate(split_long_text_by_tokens(content, encoding))
        ]
    if not chunks or not any(chunk["text"].strip() for chunk in chunks):
        raise ContentError("No usable text was found. The existing knowledge has not been replaced.")
    if len(chunks) > MAX_CHUNKS:
        raise ContentError("This source has too many sections to index in one operation.")
    return chunks
