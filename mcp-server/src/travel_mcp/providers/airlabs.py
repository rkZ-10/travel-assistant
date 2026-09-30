"""Day-of-travel flight status via AirLabs.

Docs: https://airlabs.co/docs/schedules
The `schedules` endpoint only covers a rolling ~12-hour window, and most rows on
Indian routes are codeshares (e.g. JL/QF/VS numbers sold on an IndiGo flight).
We collapse those into one row per *operating* flight.
"""
from __future__ import annotations

import re
from typing import Any

from ..models import FlightStatus, StatusResult
from .base import CachedHTTP, NotConfigured

_FLIGHT_RE = re.compile(r"^\s*([A-Z0-9]{2})\s*-?\s*(\d{1,4}[A-Z]?)\s*$", re.I)


def normalize_flight_number(value: str) -> str:
    """'6e 853' / '6E-853' / '6E853' -> '6E853'."""
    m = _FLIGHT_RE.match(value)
    if not m:
        raise ValueError(f"Not a flight number: {value!r} (expected e.g. '6E853' or 'AI 2981')")
    return f"{m.group(1).upper()}{m.group(2).upper()}"


class AirLabsStatusProvider:
    name = "airlabs"

    def __init__(self, api_key: str | None, http: CachedHTTP, ttl: int) -> None:
        self._key = api_key
        self._http = http
        self._ttl = ttl

    async def _schedules(self, **filters: str) -> tuple[list[dict[str, Any]], bool]:
        if not self._key:
            raise NotConfigured("AIRLABS_API_KEY is not set in .env")
        params = {**filters, "api_key": self._key}
        data, cached = await self._http.get_json("/schedules", params, self._ttl)
        return data.get("response") or [], cached

    async def flight_status(self, flight_number: str) -> StatusResult:
        fn = normalize_flight_number(flight_number)
        rows, cached = await self._schedules(flight_iata=fn)
        return StatusResult(flights=collapse_codeshares(rows), cached=cached)

    async def route_departures(
        self, origin: str, destination: str, airline: str | None = None
    ) -> StatusResult:
        filters = {"dep_iata": origin, "arr_iata": destination}
        if airline:
            filters["airline_iata"] = airline
        rows, cached = await self._schedules(**filters)
        return StatusResult(flights=collapse_codeshares(rows), cached=cached)


def _to_status(row: dict[str, Any], operating_fn: str, operating_airline: str) -> FlightStatus:
    return FlightStatus(
        flight_number=operating_fn,
        airline=operating_airline,
        from_airport=row.get("dep_iata") or "?",
        to_airport=row.get("arr_iata") or "?",
        status=row.get("status") or "unknown",
        scheduled_departure=row.get("dep_time") or "",
        estimated_departure=row.get("dep_estimated"),
        actual_departure=row.get("dep_actual"),
        scheduled_arrival=row.get("arr_time") or "",
        estimated_arrival=row.get("arr_estimated"),
        departure_delay_min=row.get("dep_delayed"),
        arrival_delay_min=row.get("arr_delayed"),
        departure_terminal=row.get("dep_terminal"),
        departure_gate=row.get("dep_gate"),
        arrival_terminal=row.get("arr_terminal"),
        duration_min=row.get("duration"),
    )


def collapse_codeshares(rows: list[dict[str, Any]]) -> list[FlightStatus]:
    """One entry per operating flight, with codeshare numbers listed in `marketed_as`."""
    by_key: dict[tuple[str, str], FlightStatus] = {}
    marketed: dict[tuple[str, str], list[str]] = {}

    # Operating rows first so their data wins over codeshare copies.
    for row in sorted(rows, key=lambda r: r.get("cs_flight_iata") is not None):
        cs = row.get("cs_flight_iata")
        op_fn = cs or row.get("flight_iata") or "?"
        op_airline = row.get("cs_airline_iata") if cs else row.get("airline_iata")
        key = (op_fn, row.get("dep_time_utc") or row.get("dep_time") or "")
        if key not in by_key:
            by_key[key] = _to_status(row, op_fn, op_airline or "?")
            marketed[key] = []
        if cs and row.get("flight_iata"):
            marketed[key].append(row["flight_iata"])

    out = []
    for key, status in by_key.items():
        status.marketed_as = sorted(set(marketed[key]))
        out.append(status)
    out.sort(key=lambda s: s.scheduled_departure)
    return out
