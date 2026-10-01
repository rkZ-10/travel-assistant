"""Personal travel preferences: a small JSON file the agent reads before searching
and updates when you say things like "I prefer aisle seats now".

Stored in .data/preferences.json (gitignored) so it's human-editable too.
Every change is appended to .data/preferences_history.jsonl.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .models import TravelClass

_IATA = re.compile(r"^[A-Z]{3}$")
_AIRLINE = re.compile(r"^[A-Z0-9]{2}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Seat(str, Enum):
    window = "window"
    aisle = "aisle"
    any = "any"


class FareFlexibility(str, Enum):
    cheapest = "cheapest"  # lowest price, accept high change/cancel fees
    balanced = "balanced"
    flexible = "flexible"  # prefer low cancellation/change fees


def _airlines(v: list[str] | None) -> list[str] | None:
    if v is None:
        return v
    out = [a.strip().upper() for a in v]
    bad = [a for a in out if not _AIRLINE.match(a)]
    if bad:
        raise ValueError(f"airline codes must be 2-character IATA codes (6E, AI, QP...), got {bad}")
    return list(dict.fromkeys(out))


class _Fields(BaseModel):
    home_airport: str | None = Field(None, description="Default origin, IATA code, e.g. HYD")
    preferred_airlines: list[str] | None = Field(None, description="IATA codes to favour, e.g. ['6E','AI']")
    avoid_airlines: list[str] | None = Field(None, description="IATA codes to avoid")
    cabin: TravelClass | None = None
    max_stops: int | None = Field(None, ge=0, le=2, description="0 = nonstop only")
    seat: Seat | None = None
    earliest_departure: str | None = Field(None, description="HH:MM local; skip flights leaving earlier")
    latest_departure: str | None = Field(None, description="HH:MM local; skip flights leaving later")
    checked_bag: bool | None = Field(None, description="Usually travels with a checked bag")
    fare_flexibility: FareFlexibility | None = None
    max_price: int | None = Field(None, ge=1, description="Soft budget per one-way ticket, INR")
    meal: str | None = Field(None, description="e.g. 'vegetarian'")
    notes: list[str] | None = Field(None, description="Anything else, in your words")

    @field_validator("home_airport")
    @classmethod
    def _iata(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().upper()
        if not _IATA.match(v):
            raise ValueError(f"home_airport must be a 3-letter IATA code, got {v!r}")
        return v

    @field_validator("preferred_airlines", "avoid_airlines")
    @classmethod
    def _codes(cls, v: list[str] | None) -> list[str] | None:
        return _airlines(v)

    @field_validator("earliest_departure", "latest_departure")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not _HHMM.match(v):
            raise ValueError(f"times must be HH:MM (24h), got {v!r}")
        return v


class Preferences(_Fields):
    """Saved preferences. Unset fields mean 'no preference'."""

    updated_at: str | None = None


class PreferencesUpdate(_Fields):
    """Fields to change. Omitted fields are left as they are; lists replace the old list."""

    clear: list[str] = Field(
        [], description="Field names to reset to 'no preference', e.g. ['max_price']"
    )


class PreferencesUpdateResult(BaseModel):
    preferences: Preferences
    changed: dict[str, list[Any]] = Field(description="field -> [old, new]")
    message: str


FIELD_NAMES = set(_Fields.model_fields)


class PreferenceStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "preferences.json"
        self.history_path = Path(data_dir) / "preferences_history.jsonl"

    def load(self) -> Preferences:
        if not self.path.exists():
            return Preferences()
        return Preferences.model_validate_json(self.path.read_text(encoding="utf-8"))

    def update(self, patch: PreferencesUpdate) -> tuple[Preferences, dict[str, list[Any]]]:
        unknown = set(patch.clear) - FIELD_NAMES
        if unknown:
            raise ValueError(f"unknown preference fields in clear: {sorted(unknown)}")

        current = self.load()
        data = current.model_dump(mode="json")
        changes: dict[str, list[Any]] = {}

        for name, value in patch.model_dump(mode="json", exclude_unset=True).items():
            if name == "clear" or value is None:
                continue
            if data.get(name) != value:
                changes[name] = [data.get(name), value]
                data[name] = value
        for name in patch.clear:
            if data.get(name) is not None:
                changes[name] = [data[name], None]
                data[name] = None

        if (
            data.get("earliest_departure")
            and data.get("latest_departure")
            and data["earliest_departure"] >= data["latest_departure"]
        ):
            raise ValueError("earliest_departure must be before latest_departure")
        if set(data.get("preferred_airlines") or []) & set(data.get("avoid_airlines") or []):
            raise ValueError("an airline can't be both preferred and avoided")

        if not changes:
            return current, {}

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data["updated_at"] = now
        prefs = Preferences.model_validate(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(prefs.model_dump_json(indent=2, exclude_none=False), encoding="utf-8")
        tmp.replace(self.path)
        with self.history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": now, "changes": changes}) + "\n")
        return prefs, changes
