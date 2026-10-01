from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

from ..config import REPO_ROOT

RAG_DIR = REPO_ROOT / "rag"
SOURCES_FILE = RAG_DIR / "sources.yaml"
SNAPSHOT_DIR = RAG_DIR / "snapshots"

AIRLINE_NAMES = {
    "6E": "IndiGo",
    "AI": "Air India",
    "IX": "Air India Express",
    "QP": "Akasa Air",
    "SG": "SpiceJet",
    "DGCA": "DGCA (regulator)",
}


class Source(BaseModel):
    id: str
    airline: str
    title: str
    url: str | None = None
    file: str | None = None
    topics: list[str] = []
    note: str | None = None

    @model_validator(mode="after")
    def _has_location(self) -> "Source":
        # url only: fetched over HTTP. file only: read from disk. Both: read the saved copy, cite the url.
        if not (self.url or self.file):
            raise ValueError(f"source {self.id!r}: set url, file, or both")
        self.airline = self.airline.upper()
        return self

    @property
    def airline_name(self) -> str:
        return AIRLINE_NAMES.get(self.airline, self.airline)

    def file_path(self, base: Path = RAG_DIR) -> Path:
        assert self.file
        return (base / self.file).resolve()

    @property
    def location(self) -> str:
        return self.url or f"rag/{self.file}"


def load_sources(path: Path = SOURCES_FILE) -> list[Source]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = [Source.model_validate(s) for s in raw.get("sources", [])]
    ids = [s.id for s in sources]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate source ids in {path.name}: {sorted(dupes)}")
    return sources
