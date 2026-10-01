"""Provider-neutral data models returned by MCP tools.

Kept deliberately compact: these go straight into an LLM's context window.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TravelClass(str, Enum):
    economy = "economy"
    premium_economy = "premium_economy"
    business = "business"
    first = "first"


class SortBy(str, Enum):
    best = "best"
    price = "price"
    departure = "departure"
    arrival = "arrival"
    duration = "duration"


# ---------------------------------------------------------------- search ----
class Segment(BaseModel):
    flight_number: str = Field(description="e.g. '6E 2134'")
    airline: str
    from_airport: str = Field(description="IATA code")
    to_airport: str
    departs: str = Field(description="Local time at departure airport, 'YYYY-MM-DD HH:MM'")
    arrives: str = Field(description="Local time at arrival airport, 'YYYY-MM-DD HH:MM'")
    duration_min: int
    aircraft: str | None = None
    often_delayed: bool = Field(False, description="Google flags this flight as often delayed 30+ min")
    overnight: bool = False


class Layover(BaseModel):
    airport: str
    duration_min: int
    overnight: bool = False


class Itinerary(BaseModel):
    price: int | None = Field(description="Total price in the search currency; None if unavailable")
    total_duration_min: int
    stops: int
    airlines: list[str]
    segments: list[Segment]
    layovers: list[Layover] = []
    notes: list[str] = Field([], description="Extra info from the source, e.g. fare features")
    is_best: bool = Field(False, description="In Google's 'best flights' group")
    booking_token: str | None = Field(None, description="Opaque token for a later booking-options lookup")


class PriceInsights(BaseModel):
    lowest_price: int | None = None
    price_level: str | None = Field(None, description="'low' | 'typical' | 'high' vs. history")
    typical_range: list[int] | None = None


class SearchResult(BaseModel):
    origin: str
    destination: str
    date: str
    return_date: str | None = None
    currency: str
    itineraries: list[Itinerary]
    total_found: int = Field(description="Itineraries found before truncation")
    price_insights: PriceInsights | None = None
    source_url: str | None = Field(None, description="Open these results on Google Flights")
    cached: bool = False


# ---------------------------------------------------------------- status ----
class FlightStatus(BaseModel):
    flight_number: str = Field(description="Operating flight, e.g. '6E853'")
    airline: str = Field(description="Operating airline IATA code")
    marketed_as: list[str] = Field([], description="Codeshare numbers sold on this flight")
    from_airport: str
    to_airport: str
    status: str = Field(description="scheduled | active | landed | cancelled | ...")
    scheduled_departure: str = Field(description="Local time, 'YYYY-MM-DD HH:MM'")
    estimated_departure: str | None = None
    actual_departure: str | None = None
    scheduled_arrival: str
    estimated_arrival: str | None = None
    departure_delay_min: int | None = None
    arrival_delay_min: int | None = None
    departure_terminal: str | None = None
    departure_gate: str | None = None
    arrival_terminal: str | None = None
    duration_min: int | None = None


class StatusResult(BaseModel):
    flights: list[FlightStatus]
    note: str = "AirLabs schedules cover roughly the next 12 hours only."
    cached: bool = False


class QuotaReport(BaseModel):
    provider: str
    calls_this_month: int
    monthly_budget: int
    safety_stop_at: int
    configured: bool


# --------------------------------------------------------------- policies ----
class PolicyPassage(BaseModel):
    airline: str = Field(description="IATA code, or DGCA for regulations")
    source: str = Field(description="Source page title")
    section: str = Field(description="Heading path within the page")
    text: str
    url: str
    fetched_on: str = Field(description="Date the page was captured; policies change, so cite this")
    note: str | None = Field(None, description="Caveat about this source (e.g. superseded)")
    stale_warning: str | None = Field(
        None, description="Set when the capture is old; mention it to the user alongside the answer"
    )


class PolicySearchResult(BaseModel):
    query: str
    passages: list[PolicyPassage]
    guidance: str = (
        "Answer only from these passages and cite source + fetched_on. If they don't cover the "
        "question, say so and point to the source URL rather than guessing."
    )


class PolicySource(BaseModel):
    id: str
    airline: str
    title: str
    url: str
    fetched_on: str | None
    age_days: int | None = None
    stale_warning: str | None = None
    note: str | None = None
