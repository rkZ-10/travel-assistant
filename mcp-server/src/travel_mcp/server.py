"""Travel Assistant MCP server (stdio).

Tools
  search_flights        future-dated fare search (Google Flights via SerpApi)
  get_flight_status     live status of one flight, today (AirLabs)
  get_route_departures  what's leaving on a route in the next ~12 h (AirLabs)
  get_api_usage         monthly quota used per provider
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as Date, datetime, timedelta, timezone
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .cache import QuotaExceeded, Store
from .config import Settings
from .models import QuotaReport, SearchResult, SortBy, StatusResult, TravelClass
from .providers.airlabs import AirLabsStatusProvider
from .providers.base import CachedHTTP, FlightSearchProvider, FlightStatusProvider, ProviderError

IST = timezone(timedelta(hours=5, minutes=30))
_IATA = re.compile(r"^[A-Z]{3}$")
_AIRLINE = re.compile(r"^[A-Z0-9]{2}$")

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True, idempotent_hint=True)


@dataclass
class Services:
    settings: Settings
    store: Store
    search: FlightSearchProvider
    status: FlightStatusProvider


def build_services(settings: Settings | None = None) -> Services:
    from .providers.serpapi import GoogleFlightsProvider

    s = settings or Settings.load()
    store = Store(s.data_dir / "travel_mcp.sqlite3")
    serp_http = CachedHTTP(
        "serpapi", "https://serpapi.com", store, s.serpapi_monthly_budget, s.budget_stop_ratio
    )
    air_http = CachedHTTP(
        "airlabs", "https://airlabs.co/api/v9", store, s.airlabs_monthly_budget, s.budget_stop_ratio
    )
    return Services(
        settings=s,
        store=store,
        search=GoogleFlightsProvider(
            s.serpapi_key, serp_http, s.search_ttl, s.currency, s.country, s.language
        ),
        status=AirLabsStatusProvider(s.airlabs_key, air_http, s.status_ttl),
    )


# ------------------------------------------------------------ validation ----
def _airport(value: str, field: str) -> str:
    code = value.strip().upper()
    if not _IATA.match(code):
        raise ToolError(f"{field} must be a 3-letter IATA airport code (e.g. DEL, BOM, BLR), got {value!r}")
    return code


def _date(value: str, field: str, not_before: Date) -> Date:
    try:
        d = Date.fromisoformat(value.strip())
    except ValueError:
        raise ToolError(f"{field} must be YYYY-MM-DD, got {value!r}") from None
    if d < not_before:
        raise ToolError(f"{field} {d} is before {not_before}")
    if d > datetime.now(IST).date() + timedelta(days=330):
        raise ToolError(f"{field} {d} is too far ahead; airlines publish fares ~11 months out")
    return d


# Anticipated failures: shown to the model as a readable tool error.
EXPECTED = (ProviderError, QuotaExceeded, ValueError)


# ----------------------------------------------------------------- server ----
def build_server(services: Services | None = None) -> MCPServer:
    svc = services or build_services()
    mcp = MCPServer(
        name="travel-assistant",
        version="0.1.0",
        instructions=(
            "Flight tools for an Indian travel assistant. Use search_flights for fares on a "
            "future date. Use get_flight_status / get_route_departures only for flights in "
            "the next ~12 hours. Prices are in INR. Times are local airport time. "
            "APIs are on small monthly quotas: avoid repeating identical searches."
        ),
    )

    @mcp.tool(annotations=READ_ONLY)
    async def search_flights(
        origin: Annotated[str, Field(description="Departure airport IATA code, e.g. DEL")],
        destination: Annotated[str, Field(description="Arrival airport IATA code, e.g. BOM")],
        date: Annotated[str, Field(description="Outbound date, YYYY-MM-DD")],
        return_date: Annotated[str | None, Field(description="Return date for a round trip")] = None,
        adults: Annotated[int, Field(ge=1, le=9)] = 1,
        travel_class: TravelClass = TravelClass.economy,
        nonstop_only: bool = False,
        max_price: Annotated[int | None, Field(ge=1, description="Max total price in INR")] = None,
        airlines: Annotated[
            list[str] | None,
            Field(description="Only these airline IATA codes, e.g. ['6E','AI','QP','SG','IX']"),
        ] = None,
        sort_by: SortBy = SortBy.best,
        limit: Annotated[int, Field(ge=1, le=20, description="Max itineraries returned")] = 8,
    ) -> SearchResult:
        """Search flights with live fares for a date (one-way, or round trip with return_date).

        Each call to the API uses 1 of ~250 monthly searches; identical searches
        within 30 minutes are served from cache for free.
        """
        o = _airport(origin, "origin")
        d = _airport(destination, "destination")
        if o == d:
            raise ToolError("origin and destination are the same airport")
        today = datetime.now(IST).date()
        out = _date(date, "date", today)
        ret = _date(return_date, "return_date", out).isoformat() if return_date else None
        codes = None
        if airlines:
            codes = [a.strip().upper() for a in airlines]
            bad = [a for a in codes if not _AIRLINE.match(a)]
            if bad:
                raise ToolError(f"airline codes must be 2-character IATA codes, got {bad}")
        try:
            return await svc.search.search(
                o, d, out.isoformat(), ret, adults, travel_class, nonstop_only,
                max_price, codes, sort_by, limit,
            )
        except EXPECTED as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=READ_ONLY)
    async def get_flight_status(
        flight_number: Annotated[str, Field(description="e.g. '6E853', 'AI 2981'")],
    ) -> StatusResult:
        """Live status (delay, gate, terminal) of a flight departing within ~12 hours.

        Codeshare numbers resolve to the operating flight. Not for future dates.
        """
        try:
            return await svc.status.flight_status(flight_number)
        except EXPECTED as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=READ_ONLY)
    async def get_route_departures(
        origin: Annotated[str, Field(description="Departure airport IATA code")],
        destination: Annotated[str, Field(description="Arrival airport IATA code")],
        airline: Annotated[str | None, Field(description="Optional airline IATA code, e.g. 6E")] = None,
    ) -> StatusResult:
        """Flights leaving on a route in the next ~12 hours, with live status, one row per
        operating flight (codeshares merged). Has no prices; use search_flights for fares."""
        o = _airport(origin, "origin")
        d = _airport(destination, "destination")
        a = airline.strip().upper() if airline else None
        if a and not _AIRLINE.match(a):
            raise ToolError(f"airline must be a 2-character IATA code, got {airline!r}")
        try:
            return await svc.status.route_departures(o, d, a)
        except EXPECTED as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def get_api_usage() -> list[QuotaReport]:
        """How many API calls each provider has used this month vs. its budget."""
        s = svc.settings
        rows = [
            ("serpapi", s.serpapi_monthly_budget, bool(s.serpapi_key)),
            ("airlabs", s.airlabs_monthly_budget, bool(s.airlabs_key)),
        ]
        return [
            QuotaReport(
                provider=name,
                calls_this_month=svc.store.calls_this_month(name),
                monthly_budget=budget,
                safety_stop_at=int(budget * s.budget_stop_ratio),
                configured=configured,
            )
            for name, budget, configured in rows
        ]

    return mcp


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
