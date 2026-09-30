"""SQLite-backed response cache and per-provider monthly quota tracker.

Only real network calls count against quota; cache hits are free.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class QuotaExceeded(RuntimeError):
    """Raised when a provider's monthly budget is (nearly) used up."""


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class Store:
    def __init__(self, path: Path | str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage (
                provider TEXT NOT NULL, month TEXT NOT NULL, calls INTEGER NOT NULL,
                PRIMARY KEY (provider, month)
            );
            """
        )

    # ---- cache -------------------------------------------------------------
    @staticmethod
    def make_key(provider: str, endpoint: str, params: dict[str, Any]) -> str:
        safe = {k: v for k, v in sorted(params.items()) if k not in {"api_key"}}
        raw = json.dumps([provider, endpoint, safe], sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        row = self._db.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        if row[1] < time.time():
            self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._db.commit()
            return None
        return json.loads(row[0])

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time() + ttl),
        )
        self._db.commit()

    # ---- quota -------------------------------------------------------------
    def calls_this_month(self, provider: str) -> int:
        row = self._db.execute(
            "SELECT calls FROM usage WHERE provider = ? AND month = ?",
            (provider, _month()),
        ).fetchone()
        return row[0] if row else 0

    def check_budget(self, provider: str, budget: int, stop_ratio: float) -> None:
        used = self.calls_this_month(provider)
        limit = int(budget * stop_ratio)
        if used >= limit:
            raise QuotaExceeded(
                f"{provider}: {used}/{budget} calls used this month "
                f"(safety stop at {limit}). Cached results still work."
            )

    def record_call(self, provider: str) -> None:
        self._db.execute(
            """INSERT INTO usage (provider, month, calls) VALUES (?, ?, 1)
               ON CONFLICT(provider, month) DO UPDATE SET calls = calls + 1""",
            (provider, _month()),
        )
        self._db.commit()
