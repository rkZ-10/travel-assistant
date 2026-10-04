"""Travel Assistant MCP server (stdio).

Tools
  search_flights        future-dated fare search (Google Flights via SerpApi)
  get_flight_status     live status of one flight, today (AirLabs)
  get_route_departures  what's leaving on a route in the next ~12 h (AirLabs)
  get_api_usage         monthly quota used per provider
  search_policies       baggage / fare-rule / refund / DGCA passages, with citations (RAG)
  list_policy_sources   what's indexed and when it was fetched
  get_travel_preferences / update_travel_preferences   your saved defaults
  get_booking_options   sellers, fare types and redirect links for one itinerary (UI, on click)
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
from .models import (
    BookingOptions,
    PolicyPassage,
    PolicySearchResult,
    PolicySource,
    QuotaReport,
    SearchResult,
    SortBy,
    StatusResult,
    TravelClass,
)
from .preferences import PreferenceStore, Preferences, PreferencesUpdate, PreferencesUpdateResult
from .providers.airlabs import AirLabsStatusProvider
from .providers.base import CachedHTTP, FlightSearchProvider, FlightStatusProvider, ProviderError
from .rag.index import FastEmbedder, PolicyIndex
from .rag.ingest import load_snapshot
from .rag.sources import age_days, load_sources, staleness_warning

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
    prefs: PreferenceStore | None = None
    policies: "PolicyIndex | None" = None


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
        prefs=PreferenceStore(s.prefs_dir or s.data_dir),
        policies=PolicyIndex(
            s.data_dir / "policies.sqlite3", FastEmbedder(cache_dir=s.data_dir / "models")
        ),
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
            "Flight tools for an Indian travel assistant. At the start of a trip request, call "
            "get_travel_preferences and apply them (home airport as default origin, airlines, "
            "stops, departure window, budget); say which preferences you applied. When the user "
            "states a lasting preference ('I always fly aisle', 'stop suggesting SpiceJet'), "
            "save it with update_travel_preferences; if it may be a one-off for this trip, ask "
            "first. Use search_flights for fares on a future date. Use get_flight_status / "
            "get_route_departures only for flights in the next ~12 hours. For baggage, fare "
            "rules, cancellation fees, refunds or compensation, use search_policies and answer "
            "only from its passages, citing source and fetched_on. Prices are in INR; times are "
            "local airport time. APIs are on small monthly quotas: avoid repeating searches."
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
    async def get_booking_options(
        booking_token: Annotated[str, Field(min_length=10, description="booking_token from a search_flights itinerary")],
        origin: Annotated[str, Field(description="Same origin as the search")],
        destination: Annotated[str, Field(description="Same destination as the search")],
        date: Annotated[str, Field(description="Same outbound date as the search, YYYY-MM-DD")],
        return_date: Annotated[str | None, Field(description="Same return date, for round trips")] = None,
    ) -> BookingOptions:
        """Where to book one itinerary: sellers (airline direct first), fare types with prices, and
        a redirect link (URL + form data) to the seller's page with the flight preselected.

        Costs 1 of ~250 monthly searches. Meant to be called when the user asks to book, not for
        every result. Links are short-lived (~10 minutes)."""
        o = _airport(origin, "origin")
        d = _airport(destination, "destination")
        today = datetime.now(IST).date()
        out = _date(date, "date", today)
        ret = _date(return_date, "return_date", out).isoformat() if return_date else None
        provider = svc.search
        if not hasattr(provider, "booking_options"):
            raise ToolError("the configured search provider doesn't support booking options")
        try:
            return await provider.booking_options(booking_token.strip(), o, d, out.isoformat(), ret)
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

    # ----------------------------------------------------- preferences ----
    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def get_travel_preferences() -> Preferences:
        """The user's saved travel preferences. Unset fields mean no preference."""
        if not svc.prefs:
            raise ToolError("preferences store not configured")
        return svc.prefs.load()

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        )
    )
    def update_travel_preferences(changes: PreferencesUpdate) -> PreferencesUpdateResult:
        """Save lasting preferences. Only include fields that change; lists replace the old
        value (send the full new list). Use `clear` to reset fields to no preference.
        Returns the updated preferences and a field-by-field [old, new] diff."""
        if not svc.prefs:
            raise ToolError("preferences store not configured")
        try:
            prefs, diff = svc.prefs.update(changes)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return PreferencesUpdateResult(
            preferences=prefs,
            changed=diff,
            message="no changes" if not diff else f"updated {', '.join(sorted(diff))}",
        )

    # -------------------------------------------------------- policies ----
    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def search_policies(
        query: Annotated[str, Field(description="Natural-language question, e.g. 'IndiGo Saver cancellation fee 2 days before'")],
        airlines: Annotated[
            list[str] | None, Field(description="Limit to these airline IATA codes, e.g. ['6E']")
        ] = None,
        include_regulations: Annotated[
            bool, Field(description="Also include DGCA passenger-rights rules")
        ] = True,
        top_k: Annotated[int, Field(ge=1, le=10)] = 5,
    ) -> PolicySearchResult:
        """Search official airline policy pages and DGCA rules (baggage, fare types, change and
        cancellation fees, refunds, delay/denied-boarding compensation). Returns cited passages."""
        idx = svc.policies
        if idx is None or idx.count() == 0:
            raise ToolError(
                "Policy index is empty. Run `uv run travel-rag ingest` in mcp-server/ first."
            )
        if (msg := idx.model_mismatch()):
            raise ToolError(msg)
        codes = [a.strip().upper() for a in airlines] if airlines else None
        hits = idx.search(query, codes, include_regulations, top_k)
        by_id = {src.id: src for src in load_sources()}
        return PolicySearchResult(
            query=query,
            passages=[
                PolicyPassage(
                    airline=h.airline, source=h.title, section=h.heading, text=h.text,
                    url=h.location, fetched_on=h.fetched_at[:10], note=h.note,
                    stale_warning=(
                        staleness_warning(by_id[h.source_id], h.fetched_at)
                        if h.source_id in by_id else None
                    ),
                )
                for h in hits
            ],
        )

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def list_policy_sources() -> list[PolicySource]:
        """Which policy sources are configured, and when each was last fetched."""
        out = []
        for src in load_sources():
            snap = load_snapshot(src)
            out.append(PolicySource(
                id=src.id, airline=src.airline, title=src.title, url=src.location,
                fetched_on=snap.fetched_at[:10] if snap else None,
                age_days=age_days(snap.fetched_at) if snap else None,
                stale_warning=staleness_warning(src, snap.fetched_at) if snap else None,
                note=src.note,
            ))
        return out

    return mcp


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
