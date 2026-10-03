"""Settings loaded from the repo-root .env (python-dotenv handles Windows CRLF)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    serpapi_key: str | None
    airlabs_key: str | None
    data_dir: Path
    prefs_dir: Path | None = None  # defaults to data_dir; evals point this at a per-case temp dir
    currency: str = "INR"
    country: str = "in"
    language: str = "en"
    # Monthly request budgets (free plans). Calls stop at `budget_stop_ratio` of these.
    serpapi_monthly_budget: int = 250
    airlabs_monthly_budget: int = 1000
    budget_stop_ratio: float = 0.9
    # Cache TTLs in seconds
    search_ttl: int = 30 * 60
    status_ttl: int = 5 * 60

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(REPO_ROOT / ".env")

        def clean(name: str) -> str | None:
            value = (os.getenv(name) or "").strip()
            return value or None

        data_dir = Path(os.getenv("TRAVEL_MCP_DATA_DIR") or REPO_ROOT / ".data")
        return cls(
            serpapi_key=clean("SERPAPI_KEY"),
            airlabs_key=clean("AIRLABS_API_KEY"),
            data_dir=data_dir,
            serpapi_monthly_budget=int(os.getenv("SERPAPI_MONTHLY_BUDGET", 250)),
            airlabs_monthly_budget=int(os.getenv("AIRLABS_MONTHLY_BUDGET", 1000)),
            prefs_dir=Path(p) if (p := os.getenv("TRAVEL_MCP_PREFS_DIR")) else None,
            # Evals pin search results for a day so repeated runs are free and comparable.
            search_ttl=int(os.getenv("TRAVEL_MCP_SEARCH_TTL", 30 * 60)),
        )
