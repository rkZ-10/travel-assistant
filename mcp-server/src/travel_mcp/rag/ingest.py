"""Fetch sources into dated snapshots: rag/snapshots/<id>.{html|pdf}, <id>.md, <id>.meta.json."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .extract import EXTRACTOR_VERSION, html_to_markdown, pdf_to_markdown
from .sources import SNAPSHOT_DIR, Source

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 travel-assistant-rag/0.1 (personal, non-commercial)"
)
MIN_TEXT = 300  # less than this after extraction usually means a JS-only shell or block page


@dataclass
class Snapshot:
    source_id: str
    fetched_at: str
    markdown: str
    page_title: str | None
    content_type: str
    extractor_version: int = 1


@dataclass
class FetchReport:
    source_id: str
    status: str  # fetched | cached | re-extracted | failed
    detail: str = ""


def _meta_path(d: Path, sid: str) -> Path:
    return d / f"{sid}.meta.json"


def load_snapshot(source: Source, snap_dir: Path = SNAPSHOT_DIR) -> Snapshot | None:
    meta_p, md_p = _meta_path(snap_dir, source.id), snap_dir / f"{source.id}.md"
    if not (meta_p.exists() and md_p.exists()):
        return None
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    return Snapshot(
        source.id, meta["fetched_at"], md_p.read_text(encoding="utf-8"),
        meta.get("page_title"), meta.get("content_type", ""),
        meta.get("extractor_version", 1),
    )


def reextract_snapshot(source: Source, snap_dir: Path = SNAPSHOT_DIR) -> Snapshot | None:
    """Re-run extraction on the saved raw page (after an extractor upgrade). Keeps fetched_at:
    the content is as old as when it was captured, not when we re-parsed it."""
    meta_p = _meta_path(snap_dir, source.id)
    raw_p = next((p for p in (snap_dir / f"{source.id}.html", snap_dir / f"{source.id}.pdf") if p.exists()), None)
    if not (meta_p.exists() and raw_p):
        return None
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    md, title, ctype = _extract(raw_p.read_bytes(), meta.get("content_type", ""), str(raw_p))
    (snap_dir / f"{source.id}.md").write_text(md, encoding="utf-8")
    meta.update(page_title=title or meta.get("page_title"), chars=len(md), extractor_version=EXTRACTOR_VERSION)
    meta_p.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return Snapshot(source.id, meta["fetched_at"], md, meta.get("page_title"), ctype, EXTRACTOR_VERSION)


def _extract(raw: bytes, content_type: str, hint: str) -> tuple[str, str | None, str]:
    is_pdf = "pdf" in content_type or raw[:5] == b"%PDF-" or hint.lower().endswith(".pdf")
    if is_pdf:
        return pdf_to_markdown(raw), None, "application/pdf"
    html = raw.decode("utf-8", errors="replace")
    md, title = html_to_markdown(html)
    return md, title, "text/html"


def fetch_source(
    source: Source,
    snap_dir: Path = SNAPSHOT_DIR,
    client: httpx.Client | None = None,
) -> Snapshot:
    if source.file:
        path = source.file_path()
        if not path.exists():
            where = f"open {source.url} in a browser and save it as" if source.url else "add"
            raise FileNotFoundError(f"{where} rag/{source.file}")
        raw, ctype = path.read_bytes(), ""
        hint = str(path)
    else:
        own = client is None
        client = client or httpx.Client(timeout=45, follow_redirects=True, headers={"User-Agent": UA})
        try:
            resp = client.get(source.url)  # type: ignore[arg-type]
            resp.raise_for_status()
        finally:
            if own:
                client.close()
        raw, ctype, hint = resp.content, resp.headers.get("content-type", ""), source.url or ""

    md, title, ctype = _extract(raw, ctype, hint)
    if len(md) < MIN_TEXT:
        raise ValueError(
            f"only {len(md)} chars of text extracted — page may need JavaScript or blocked the request"
        )

    snap_dir.mkdir(parents=True, exist_ok=True)
    ext = "pdf" if ctype == "application/pdf" else "html"
    (snap_dir / f"{source.id}.{ext}").write_bytes(raw)
    (snap_dir / f"{source.id}.md").write_text(md, encoding="utf-8")
    # A saved copy is as fresh as the day it was saved, not the day it was ingested.
    when = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) if source.file else datetime.now(timezone.utc)
    fetched_at = when.isoformat(timespec="seconds")
    _meta_path(snap_dir, source.id).write_text(
        json.dumps(
            {
                "source_id": source.id,
                "location": source.location,
                "fetched_at": fetched_at,
                "content_type": ctype,
                "page_title": title,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "chars": len(md),
                "extractor_version": EXTRACTOR_VERSION,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return Snapshot(source.id, fetched_at, md, title, ctype, EXTRACTOR_VERSION)


def fetch_all(
    sources: list[Source],
    snap_dir: Path = SNAPSHOT_DIR,
    refresh: bool = False,
    max_age_days: int = 30,
    client: httpx.Client | None = None,
) -> list[FetchReport]:
    reports = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    for s in sources:
        existing = load_snapshot(s, snap_dir)
        reextracted = False
        if existing and existing.extractor_version != EXTRACTOR_VERSION:
            existing = reextract_snapshot(s, snap_dir) or existing
            reextracted = existing.extractor_version == EXTRACTOR_VERSION
        if not existing:
            stale = True
        elif s.file:  # local files are cheap to read: re-read whenever a newer copy has been saved
            path = s.file_path()
            saved = datetime.fromisoformat(existing.fetched_at).timestamp()
            stale = not path.exists() or int(path.stat().st_mtime) > saved  # fetched_at is whole seconds
        else:
            stale = datetime.fromisoformat(existing.fetched_at) <= cutoff
        if not refresh and not stale:
            status = "re-extracted" if reextracted else "cached"
            reports.append(FetchReport(s.id, status, existing.fetched_at[:10]))
            continue
        try:
            snap = fetch_source(s, snap_dir, client)
            reports.append(FetchReport(s.id, "fetched", f"{len(snap.markdown)} chars"))
        except Exception as exc:  # noqa: BLE001 - report and keep going
            note = " (keeping older snapshot)" if existing else ""
            reports.append(FetchReport(s.id, "failed", f"{exc.__class__.__name__}: {exc}{note}"))
    return reports
