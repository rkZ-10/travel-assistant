"""Flight search via SerpApi's Google Flights engine.

Docs: https://serpapi.com/google-flights-api
"""
from __future__ import annotations

from typing import Any

from ..models import (
    BookingOption,
    BookingOptions,
    Itinerary,
    Layover,
    PriceInsights,
    SearchResult,
    Segment,
    SortBy,
    TravelClass,
)
from .base import CachedHTTP, NotConfigured, ProviderError

_CLASS = {
    TravelClass.economy: 1,
    TravelClass.premium_economy: 2,
    TravelClass.business: 3,
    TravelClass.first: 4,
}
_SORT = {
    SortBy.best: 1,
    SortBy.price: 2,
    SortBy.departure: 3,
    SortBy.arrival: 4,
    SortBy.duration: 5,
}


BOOKING_TTL = 10 * 60  # redirect links are short-lived


class GoogleFlightsProvider:
    name = "serpapi"

    def __init__(
        self,
        api_key: str | None,
        http: CachedHTTP,
        ttl: int,
        currency: str = "INR",
        country: str = "in",
        language: str = "en",
    ) -> None:
        self._key = api_key
        self._http = http
        self._ttl = ttl
        self._currency = currency
        self._country = country
        self._language = language

    async def search(
        self,
        origin: str,
        destination: str,
        date: str,
        return_date: str | None = None,
        adults: int = 1,
        travel_class: TravelClass = TravelClass.economy,
        nonstop_only: bool = False,
        max_price: int | None = None,
        airlines: list[str] | None = None,
        sort_by: SortBy = SortBy.best,
        limit: int = 8,
    ) -> SearchResult:
        if not self._key:
            raise NotConfigured("SERPAPI_KEY is not set in .env")

        params: dict[str, Any] = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": date,
            "type": 1 if return_date else 2,
            "adults": adults,
            "travel_class": _CLASS[travel_class],
            "sort_by": _SORT[sort_by],
            "currency": self._currency,
            "gl": self._country,
            "hl": self._language,
        }
        if return_date:
            params["return_date"] = return_date
        if nonstop_only:
            params["stops"] = 1
        if max_price:
            params["max_price"] = max_price
        if airlines:
            params["include_airlines"] = ",".join(airlines)

        params["api_key"] = self._key  # stripped from the cache key by Store.make_key
        data, cached = await self._http.get_json("/search.json", params, self._ttl)

        return parse_search(
            data,
            origin=origin,
            destination=destination,
            date=date,
            return_date=return_date,
            currency=self._currency,
            limit=limit,
            cached=cached,
            max_price=max_price,
        )


    async def booking_options(
        self, booking_token: str, origin: str, destination: str, date: str, return_date: str | None = None
    ) -> BookingOptions:
        """Sellers, fare types and redirect links for one itinerary. Costs 1 search: call only
        when the user asks to book."""
        if not self._key:
            raise NotConfigured("SERPAPI_KEY is not set in .env")
        params = _search_params_for_booking(
            origin, destination, date, return_date, self._currency, self._country, self._language
        )
        params["booking_token"] = booking_token
        params["api_key"] = self._key
        data, _ = await self._http.get_json("/search.json", params, BOOKING_TTL)
        return parse_booking_options(data)


def _search_params_for_booking(
    origin: str, destination: str, date: str, return_date: str | None, currency: str, country: str, language: str
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "engine": "google_flights", "departure_id": origin, "arrival_id": destination,
        "outbound_date": date, "type": 1 if return_date else 2,
        "currency": currency, "gl": country, "hl": language,
    }
    if return_date:
        params["return_date"] = return_date
    return params


def _segment(raw: dict[str, Any]) -> Segment:
    dep, arr = raw.get("departure_airport", {}), raw.get("arrival_airport", {})
    return Segment(
        flight_number=raw.get("flight_number", "?"),
        airline=raw.get("airline", "?"),
        from_airport=dep.get("id", "?"),
        to_airport=arr.get("id", "?"),
        departs=dep.get("time", ""),
        arrives=arr.get("time", ""),
        duration_min=int(raw.get("duration") or 0),
        aircraft=raw.get("airplane"),
        often_delayed=bool(raw.get("often_delayed_by_over_30_min")),
        overnight=bool(raw.get("overnight")),
    )


def _itinerary(raw: dict[str, Any], is_best: bool) -> Itinerary:
    segments = [_segment(s) for s in raw.get("flights", [])]
    airlines = list(dict.fromkeys(s.airline for s in segments))
    notes: list[str] = []
    for s in raw.get("flights", []):
        notes.extend(s.get("extensions", []) or [])
    notes.extend(raw.get("extensions", []) or [])
    return Itinerary(
        price=raw.get("price"),
        total_duration_min=int(raw.get("total_duration") or sum(s.duration_min for s in segments)),
        stops=max(len(segments) - 1, 0),
        airlines=airlines,
        segments=segments,
        layovers=[
            Layover(
                airport=l.get("id", "?"),
                duration_min=int(l.get("duration") or 0),
                overnight=bool(l.get("overnight")),
            )
            for l in raw.get("layovers", []) or []
        ],
        notes=list(dict.fromkeys(notes))[:6],
        is_best=is_best,
        booking_token=raw.get("booking_token"),
    )


def parse_search(
    data: dict[str, Any],
    *,
    origin: str,
    destination: str,
    date: str,
    return_date: str | None,
    currency: str,
    limit: int,
    cached: bool,
    max_price: int | None = None,
) -> SearchResult:
    best = [_itinerary(r, True) for r in data.get("best_flights", []) or []]
    other = [_itinerary(r, False) for r in data.get("other_flights", []) or []]
    all_its = best + other
    if not all_its and "search_metadata" not in data:
        raise ProviderError("serpapi: unexpected response shape")

    notes: list[str] = []
    if max_price:
        # When nothing fits the budget, Google returns unpriced or over-budget itineraries
        # instead of an empty list. Don't let those pass as matches.
        fits = [i for i in all_its if i.price is not None and i.price <= max_price]
        dropped = len(all_its) - len(fits)
        if dropped:
            notes.append(
                f"Removed {dropped} itinerary(ies) without a price or above the {currency} {max_price} limit."
            )
        if not fits:
            notes.append(
                f"No flights found at or under {currency} {max_price}. To show the cheapest available "
                "fare, search again without max_price and tell the user it is over budget."
            )
        all_its = fits

    pi = data.get("price_insights")
    insights = (
        PriceInsights(
            lowest_price=pi.get("lowest_price"),
            price_level=pi.get("price_level"),
            typical_range=pi.get("typical_price_range"),
        )
        if pi
        else None
    )
    return SearchResult(
        origin=origin,
        destination=destination,
        date=date,
        return_date=return_date,
        currency=currency,
        itineraries=all_its[:limit],
        total_found=len(all_its),
        price_insights=insights,
        source_url=(data.get("search_metadata") or {}).get("google_flights_url"),
        cached=cached,
        notes=notes,
        fetched_at=data.get("_fetched_at"),
    )


def _booking_option(raw: dict[str, Any], leg: str) -> BookingOption:
    req = raw.get("booking_request") or {}
    bags = raw.get("baggage_prices") or []
    return BookingOption(
        seller=raw.get("book_with") or "Unknown seller",
        is_airline=bool(raw.get("airline")),
        fare_name=raw.get("option_title"),
        price=raw.get("price"),
        leg=leg,
        flight_numbers=list(raw.get("marketed_as") or []),
        features=list(raw.get("extensions") or [])[:6],
        baggage=[str(b) for b in bags][:4] if isinstance(bags, list) else [],
        booking_url=req.get("url"),
        booking_post_data=req.get("post_data"),
        booking_phone=raw.get("booking_phone"),
    )


def parse_booking_options(data: dict[str, Any]) -> BookingOptions:
    options: list[BookingOption] = []
    for item in data.get("booking_options") or []:
        if "together" in item:
            options.append(_booking_option(item["together"], "together"))
        for leg in ("departing", "returning"):
            if leg in item:
                options.append(_booking_option(item[leg], leg))
    # Airline-direct first, then cheapest.
    options.sort(key=lambda o: (not o.is_airline, o.price if o.price is not None else 10**9))
    notes = []
    if not options:
        notes.append("Google returned no booking options for this flight; use the Google Flights link instead.")
    elif not any(o.is_airline for o in options):
        notes.append("No airline-direct option was offered for this flight; only travel sites.")
    return BookingOptions(options=options, fetched_at=data.get("_fetched_at"), notes=notes)
