"""SQLite policy index: FTS5 (BM25) for exact terms + dense vectors for meaning,
fused with Reciprocal Rank Fusion. Brute-force cosine is fine at this size (~1-2k chunks)."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .chunk import chunk_markdown
from .ingest import load_snapshot
from .sources import SNAPSHOT_DIR, Source

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
RRF_K = 60
_STOP = set(
    "a an and are as at be by can do does for from how i if in is it my of on or the to was "
    "what when where which who will with you your me there any".split()
)


class Embedder(Protocol):
    model_name: str

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


class FastEmbedder:
    """Local ONNX embeddings via fastembed (model downloads once, ~70 MB)."""

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_dir: Path | None = None) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir  # default fastembed cache lives in %TEMP%, which gets wiped
        self._model = None

    def _m(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(
                self.model_name, cache_dir=str(self.cache_dir) if self.cache_dir else None
            )
        return self._model

    @staticmethod
    def _norm(a: np.ndarray) -> np.ndarray:
        return (a / np.linalg.norm(a, axis=-1, keepdims=True)).astype(np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._norm(np.array(list(self._m().passage_embed(texts))))

    def embed_query(self, text: str) -> np.ndarray:
        return self._norm(np.array(list(self._m().query_embed(text)))[0])


@dataclass
class Hit:
    source_id: str
    airline: str
    title: str
    heading: str
    text: str
    location: str
    fetched_at: str
    note: str | None
    score: float


def fts_query(q: str) -> str:
    tokens = [t for t in re.findall(r"[\w₹]+", q.lower()) if t not in _STOP and len(t) > 1]
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(tokens))


class PolicyIndex:
    def __init__(self, path: Path | str, embedder: Embedder) -> None:
        self.path = path
        self.embedder = embedder
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY, source_id TEXT, airline TEXT, title TEXT, heading TEXT,
                text TEXT, location TEXT, fetched_at TEXT, note TEXT, vec BLOB
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                title, heading, text, content='chunks', content_rowid='id'
            );
            """
        )
        self._vecs: np.ndarray | None = None
        self._rows: list[tuple] | None = None

    # ------------------------------------------------------------ build ----
    def rebuild(self, sources: list[Source], snap_dir: Path = SNAPSHOT_DIR) -> dict[str, int]:
        counts: dict[str, int] = {}
        records = []
        for s in sources:
            snap = load_snapshot(s, snap_dir)
            if not snap:
                continue
            chunks = chunk_markdown(snap.markdown)
            counts[s.id] = len(chunks)
            for c in chunks:
                records.append((s, snap.fetched_at, c))
        # Contextual header in the embedded text; stored text stays clean for citation.
        embed_texts = [
            f"{s.airline_name} — {s.title}. {c.heading}\n{c.text}" for s, _, c in records
        ]
        vecs = self.embedder.embed_documents(embed_texts) if records else np.zeros((0, 1))

        with self.db:
            self.db.execute("DELETE FROM chunks")
            self.db.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('delete-all')")
            for (s, fetched_at, c), v in zip(records, vecs):
                cur = self.db.execute(
                    "INSERT INTO chunks (source_id, airline, title, heading, text, location, "
                    "fetched_at, note, vec) VALUES (?,?,?,?,?,?,?,?,?)",
                    (s.id, s.airline, s.title, c.heading, c.text, s.location, fetched_at,
                     s.note, np.asarray(v, dtype=np.float32).tobytes()),
                )
                self.db.execute(
                    "INSERT INTO chunks_fts(rowid, title, heading, text) VALUES (?,?,?,?)",
                    (cur.lastrowid, s.title, c.heading, c.text),
                )
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES ('model', ?)", (self.embedder.model_name,)
            )
        self._vecs = self._rows = None
        return counts

    # ----------------------------------------------------------- search ----
    def _load(self) -> None:
        if self._rows is not None:
            return
        rows = self.db.execute(
            "SELECT id, source_id, airline, title, heading, text, location, fetched_at, note, vec "
            "FROM chunks ORDER BY id"
        ).fetchall()
        self._rows = [r[:9] for r in rows]
        self._vecs = (
            np.vstack([np.frombuffer(r[9], dtype=np.float32) for r in rows]) if rows else None
        )

    def model_mismatch(self) -> str | None:
        row = self.db.execute("SELECT v FROM meta WHERE k='model'").fetchone()
        if row and row[0] != self.embedder.model_name:
            return f"index built with {row[0]}, current embedder is {self.embedder.model_name}; re-run ingest"
        return None

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def search(
        self,
        query: str,
        airlines: list[str] | None = None,
        include_regulations: bool = True,
        top_k: int = 5,
        pool: int = 25,
    ) -> list[Hit]:
        self._load()
        if not self._rows:
            return []
        allowed = None
        if airlines:
            allowed = {a.upper() for a in airlines} | ({"DGCA"} if include_regulations else set())
        by_id = {r[0]: r for r in self._rows}
        ok = lambda rid: allowed is None or by_id[rid][2] in allowed  # noqa: E731

        # Dense ranking
        qv = self.embedder.embed_query(query)
        sims = self._vecs @ qv
        dense = [self._rows[i][0] for i in np.argsort(-sims) if ok(self._rows[i][0])][:pool]

        # Keyword ranking (BM25)
        sparse: list[int] = []
        fq = fts_query(query)
        if fq:
            sparse = [
                rid for (rid,) in self.db.execute(
                    "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fq, pool * 3),
                ) if ok(rid)
            ][:pool]

        fused: dict[int, float] = {}
        for ranking in (dense, sparse):
            for rank, rid in enumerate(ranking):
                fused[rid] = fused.get(rid, 0.0) + 1.0 / (RRF_K + rank + 1)

        best = sorted(fused.items(), key=lambda kv: -kv[1])[:top_k]
        return [
            Hit(*by_id[rid][1:9], score=round(score, 4))  # type: ignore[arg-type]
            for rid, score in best
        ]
