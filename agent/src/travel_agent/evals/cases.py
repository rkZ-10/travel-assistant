"""Eval case definitions (evals/cases.yaml) and date placeholders.

Prompts and expected args can use relative dates so cases never go stale:
  {date+14}  -> "Friday 16 October 2026"   (for prompts)
  {iso+14}   -> "2026-10-16"                (for expected tool args)
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ..config import REPO_ROOT
from ..prompts import IST

CASES_FILE = REPO_ROOT / "evals" / "cases.yaml"
_PLACEHOLDER = re.compile(r"\{(date|iso)([+-]\d+)\}")


def render(value: Any, today: date | None = None) -> Any:
    today = today or datetime.now(IST).date()

    def sub(m: re.Match) -> str:
        d = today + timedelta(days=int(m.group(2)))
        return d.isoformat() if m.group(1) == "iso" else f"{d:%A} {d.day} {d:%B %Y}"

    if isinstance(value, str):
        return _PLACEHOLDER.sub(sub, value)
    if isinstance(value, list):
        return [render(v, today) for v in value]
    if isinstance(value, dict):
        return {k: render(v, today) for k, v in value.items()}
    return value


class ToolArgCheck(BaseModel):
    tool: str
    args: dict[str, Any]


class Checks(BaseModel):
    tools_include: list[str] = []
    tools_exclude: list[str] = []
    first_tool: str | None = None
    max_calls: dict[str, int] = {}
    tool_args: list[ToolArgCheck] = []
    denied: list[str] = []
    answer_matches: list[str] = []
    answer_not_matches: list[str] = []
    asks_question: bool = False
    cites_policy_date: bool = False
    grounded_amounts: bool = False
    tools_ok: list[str] = []  # every call to these tools must succeed (not is_error)


class Case(BaseModel):
    id: str
    prompt: str
    tags: list[str] = []
    why: str = Field("", description="What behaviour this case protects")
    preferences: dict[str, Any] = {}
    approve_preference_writes: bool = False
    ui: bool = Field(False, description="Run with the web-UI display tools (show_flight_cards)")
    checks: Checks

    def rendered(self, today: date | None = None) -> "Case":
        return Case.model_validate(render(self.model_dump(), today))


def load_cases(path: Path = CASES_FILE) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = [Case.model_validate(c) for c in raw.get("cases", [])]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in cases.yaml")
    return cases
