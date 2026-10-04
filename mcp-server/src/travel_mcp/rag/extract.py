"""Turn HTML / PDF into lightweight markdown: headings, paragraphs, bullet lists, and
tables as pipe rows (fee tables are the most-asked content, so they must survive)."""
from __future__ import annotations

import io
import json
import re

from bs4 import BeautifulSoup, NavigableString, Tag

# Bump when extraction output changes: `ingest` then re-extracts saved snapshots without re-fetching.
EXTRACTOR_VERSION = 3

_DROP = ["script", "style", "noscript", "svg", "iframe", "button", "nav", "footer", "header",
         "input", "select", "textarea"]
# ASP.NET (e.g. SpiceJet) wraps the whole page in one <form>. A form with this much text is the
# page, so keep its content; smaller forms are search/booking widgets and are dropped.
_PAGE_FORM_CHARS = 2000
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


_ACCORDION_HEADER = re.compile(r"accordion.*(header|title|heading|toggle)", re.I)
_BOLD_HEADING_MAX = 120


def _tab_labels(soup: BeautifulSoup) -> None:
    """Label each ARIA tab panel ("Domestic", "International"...) before buttons are dropped.

    Fee pages put Domestic/International in tabs, not headings; without this every table
    would inherit whatever real heading came before it.
    """
    for panel in soup.select('[role="tabpanel"]'):
        label = None
        if (tab_id := panel.get("aria-labelledby")) and (tab := soup.find(id=tab_id)):
            label = _clean(tab.get_text(" "))
        label = label or _clean(panel.get("aria-label") or "")
        if not label and (layer := panel.get("data-cmp-data-layer")):  # Adobe AEM core tabs
            try:
                label = next(iter(json.loads(layer).values())).get("dc:title")
            except (ValueError, StopIteration, AttributeError):
                label = None
        if label:
            panel["data-rag-heading"] = label


def _is_accordion_header(tag: Tag) -> bool:
    return any(_ACCORDION_HEADER.search(c) for c in tag.get("class", [])) or tag.name == "summary"


def _bold_heading(tag: Tag) -> str | None:
    """<p><b>Booking Fee</b></p> style pseudo-headings."""
    if tag.name != "p" or tag.find(["table", "ul", "ol"]):
        return None
    bold = tag.find(["b", "strong"])
    text = _clean(tag.get_text(" "))
    if bold and text and text == _clean(bold.get_text(" ")) and len(text) <= _BOLD_HEADING_MAX:
        return text
    return None


def html_to_markdown(html: str) -> tuple[str, str | None]:
    """Returns (markdown, page_title).

    Heading levels follow the page's *visual* structure: a tab panel or accordion item opens
    a level, and h-tags / bold pseudo-headings inside it nest below that level.
    """
    soup = BeautifulSoup(html, "html.parser")
    title = _clean(soup.title.get_text()) if soup.title else None
    _tab_labels(soup)
    for tag in soup(_DROP):
        tag.decompose()
    for form in soup.find_all("form"):
        if len(form.get_text(" ", strip=True)) >= _PAGE_FORM_CHARS:
            form.unwrap()
        else:
            form.decompose()
    # Cookie banners / modals. Inactive tab panels are often aria-hidden; keep those.
    for tag in soup.select('[class*="cookie"], [id*="cookie"], [aria-hidden="true"]'):
        if not tag.get("data-rag-heading"):
            tag.decompose()
    root = soup.find("main") or soup.body or soup

    out: list[str] = []
    path: dict[int, str] = {}  # level -> heading text, for de-duplication scope
    seen: set[tuple[str, str]] = set()

    def heading(level: int, text: str) -> int:
        """Open a heading; returns the level actually used. Over-long "headings" (some
        accordions put a whole paragraph in the title) are kept as text instead."""
        if len(text) > _BOLD_HEADING_MAX:
            emit(text)
            return level
        level = min(level, 6)
        for k in [k for k in path if k >= level]:
            del path[k]
        path[level] = text
        out.append("#" * level + " " + text)
        return level

    def synthetic(ctx: int) -> int:
        # Tabs/accordions sit under the page's own h1, never beside it.
        return max(ctx + 1, 2 if 1 in path else 1)

    def emit(block: str) -> None:
        # Drop exact repeats within the same section (AEM ships desktop + mobile copies),
        # but keep identical tables that appear under different tabs/sections.
        key = (" > ".join(path[k] for k in sorted(path)), block)
        if key not in seen:
            seen.add(key)
            out.append(block)

    def walk(node: Tag, ctx: int) -> None:
        sib_ctx = ctx  # accordion header raises the level for the body that follows it
        for child in node.children:
            if isinstance(child, NavigableString) or not isinstance(child, Tag):
                continue
            name = child.name
            if label := child.get("data-rag-heading"):
                walk(child, heading(synthetic(ctx), label))
                sib_ctx = ctx
            elif _is_accordion_header(child):
                text = _clean(child.get_text(" "))
                if text:
                    sib_ctx = heading(synthetic(ctx), text)
            elif name == "table":
                md = _table_md(child)
                if md:
                    emit(md)
            elif name and re.fullmatch(r"h[1-6]", name):
                text = _clean(child.get_text(" "))
                if text:
                    heading(max(int(name[1]), sib_ctx + 1), text)
            elif (bold := _bold_heading(child)) is not None:
                heading(sib_ctx + 1, bold)
            elif name == "li":
                text = _clean(child.get_text(" "))
                if text:
                    emit("- " + text)
            elif name in _BLOCK:
                text = _clean(child.get_text(" "))
                if text:
                    emit(text)
            elif child.find(list(_BLOCK)) is not None or child.find(attrs={"data-rag-heading": True}):
                walk(child, sib_ctx)
            else:
                text = _clean(child.get_text(" "))
                if len(text) > 30:  # stray text in divs; skip tiny UI labels
                    emit(text)

    walk(root, 0)
    return "\n\n".join(out), title


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
