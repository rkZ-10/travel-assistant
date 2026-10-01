"""Turn HTML / PDF into lightweight markdown: headings, paragraphs, bullet lists, and
tables as pipe rows (fee tables are the most-asked content, so they must survive)."""
from __future__ import annotations

import io
import re

from bs4 import BeautifulSoup, NavigableString, Tag

_DROP = ["script", "style", "noscript", "svg", "iframe", "form", "button", "nav", "footer", "header"]
_BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "dt", "dd", "blockquote"}
_WS = re.compile(r"[ \t\r\f\v ]+")


def _clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _table_md(table: Tag) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def html_to_markdown(html: str) -> tuple[str, str | None]:
    """Returns (markdown, page_title)."""
    soup = BeautifulSoup(html, "html.parser")
    title = _clean(soup.title.get_text()) if soup.title else None
    for tag in soup(_DROP):
        tag.decompose()
    # Cookie banners / modals often carry these markers.
    for tag in soup.select('[class*="cookie"], [id*="cookie"], [aria-hidden="true"]'):
        tag.decompose()
    root = soup.find("main") or soup.body or soup

    out: list[str] = []

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString) or not isinstance(child, Tag):
                continue
            name = child.name
            if name == "table":
                md = _table_md(child)
                if md:
                    out.append(md)
            elif name and re.fullmatch(r"h[1-6]", name):
                text = _clean(child.get_text(" "))
                if text:
                    out.append("#" * int(name[1]) + " " + text)
            elif name == "li":
                text = _clean(child.get_text(" "))
                if text:
                    out.append("- " + text)
            elif name in _BLOCK:
                text = _clean(child.get_text(" "))
                if text:
                    out.append(text)
            elif child.find(list(_BLOCK)) is not None:
                walk(child)
            else:
                text = _clean(child.get_text(" "))
                if len(text) > 30:  # stray text in divs; skip tiny UI labels
                    out.append(text)

    walk(root)
    # Drop exact duplicate blocks (AEM pages often repeat mobile/desktop copies).
    seen: set[str] = set()
    deduped = [b for b in out if not (b in seen or seen.add(b))]
    return "\n\n".join(deduped), title


def pdf_to_markdown(data: bytes) -> str:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            parts = [f"## Page {i}"]
            text = page.extract_text() or ""
            parts.append(text.strip())
            for table in page.extract_tables() or []:
                rows = [
                    "| " + " | ".join(_clean(c or "") for c in row) + " |"
                    for row in table
                    if any(row)
                ]
                if rows:
                    parts.append("\n".join(rows))
            pages.append("\n\n".join(p for p in parts if p))
    return "\n\n".join(pages)
