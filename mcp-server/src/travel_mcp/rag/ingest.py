"""Fetch sources into dated snapshots: rag/snapshots/<id>.{html|pdf}, <id>.md, <id>.meta.json."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .extract import html_to_markdown, pdf_to_markdown
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


@dataclass
class FetchReport:
    source_id: str
    status: str  # fetched | cached | failed
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
    )


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
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
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
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return Snapshot(source.id, fetched_at, md, title, ctype)


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
        if existing and not refresh and datetime.fromisoformat(existing.fetched_at) > cutoff:
            reports.append(FetchReport(s.id, "cached", existing.fetched_at[:10]))
            continue
        try:
            snap = fetch_source(s, snap_dir, client)
            reports.append(FetchReport(s.id, "fetched", f"{len(snap.markdown)} chars"))
        except Exception as exc:  # noqa: BLE001 - report and keep going
            note = " (keeping older snapshot)" if existing else ""
            reports.append(FetchReport(s.id, "failed", f"{exc.__class__.__name__}: {exc}{note}"))
    return reports
