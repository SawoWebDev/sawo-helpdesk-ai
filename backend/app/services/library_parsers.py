"""Text extraction for Library ingestion: PDF, DOCX, and crawled web pages.
Each parser returns plain text only — chunking happens separately in
app.services.chunking."""

import io

import httpx
from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader

CRAWL_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
CRAWL_USER_AGENT = "Mozilla/5.0 (compatible; HelpdeskLibraryBot/1.0)"


class ParseError(Exception):
    pass


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ParseError(f"Failed to parse PDF: {exc}") from exc
    return "\n\n".join(p.strip() for p in pages if p.strip())


def extract_docx_text(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
        paragraphs = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                paragraphs.append(" | ".join(cell.text for cell in row.cells))
    except Exception as exc:
        raise ParseError(f"Failed to parse DOCX: {exc}") from exc
    return "\n".join(p.strip() for p in paragraphs if p.strip())


def extract_xlsx_text(data: bytes) -> str:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise ParseError(f"Failed to parse XLSX: {exc}") from exc

    lines: list[str] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            cells = [str(v).strip() for v in row if v is not None and str(v).strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


# Strip only what genuinely cannot render as readable text (raw script/style
# source code, SVG markup) — capture everything else verbatim, including nav
# menus, headers/footers, and forms. No guessing at "chrome" vs "real
# content": whatever text is actually on the crawled page goes into the
# Library as-is.
_STRIP_TAGS = [
    "script",
    "style",
    "svg",
]


def extract_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag_name in _STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    body = soup.body or soup
    text = body.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


async def fetch_url(url: str) -> tuple[str, str]:
    """Returns (html, final_url)."""
    try:
        async with httpx.AsyncClient(
            timeout=CRAWL_TIMEOUT, follow_redirects=True, headers={"User-Agent": CRAWL_USER_AGENT}
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text, str(resp.url)
    except httpx.HTTPError as exc:
        raise ParseError(f"Failed to fetch URL: {exc}") from exc


def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        absolute = httpx.URL(base_url).join(href)
        if absolute.scheme in ("http", "https"):
            links.append(str(absolute.copy_with(fragment=None)))
    return links


def extract_text_for_file(filename: str, data: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return extract_pdf_text(data)
    if ext == "docx":
        return extract_docx_text(data)
    if ext == "xlsx":
        return extract_xlsx_text(data)
    raise ParseError(f"Unsupported file type: .{ext}")
