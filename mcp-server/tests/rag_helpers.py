"""Offline helpers: a deterministic bag-of-words embedder and synthetic snapshot writer."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from travel_mcp.rag.sources import Source

DIM = 512


class FakeEmbedder:
    model_name = "fake-bow-512"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(DIM, dtype=np.float32)
        for tok in re.findall(r"[a-z]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed_documents(self, texts):
        return np.vstack([self._vec(t) for t in texts]) if texts else np.zeros((0, DIM))

    def embed_query(self, text):
        return self._vec(text)


def write_snapshot(snap_dir: Path, source: Source, markdown: str, fetched_at="2026-10-02T00:00:00+00:00"):
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / f"{source.id}.md").write_text(markdown, encoding="utf-8")
    (snap_dir / f"{source.id}.meta.json").write_text(
        json.dumps({"fetched_at": fetched_at, "content_type": "text/html"}), encoding="utf-8"
    )


SOURCES = [
    Source(id="t-indigo-fees", airline="6E", title="IndiGo — Fees and charges", url="https://example.test/6e/fees"),
    Source(id="t-akasa-bag", airline="QP", title="Akasa — Baggage", url="https://example.test/qp/bag"),
    Source(id="t-dgca", airline="DGCA", title="DGCA CAR M-IV", url="https://example.test/dgca.pdf",
           note="Test note: verify current revision."),
]

AKASA_MD = """# Baggage

## Checked baggage
Domestic flights include 1 piece of 15 kg checked baggage. Hand baggage: one bag up to 7 kg.

## Excess baggage
Excess baggage at the airport is charged at INR 700 per kg on domestic flights."""

DGCA_MD = """# Facilities to passengers

## Denied boarding
If boarding is denied and an alternate flight is arranged within 24 hours, compensation is 200% of the
booked one-way basic fare plus fuel charge, subject to a maximum of INR 10,000.

## Cancellation of flights
Passengers informed less than two weeks before departure shall be offered an alternate flight or a full refund."""
