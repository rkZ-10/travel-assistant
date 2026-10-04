"""Provider interfaces + a shared cached/quota-aware HTTP helper."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from ..cache import Store
from ..models import SearchResult, SortBy, StatusResult, TravelClass


class ProviderError(RuntimeError):
    """The upstream API returned an error or unusable response."""


class NotConfigured(ProviderError):
    """The provider's API key is missing from .env."""


class FlightSearchProvider(Protocol):
    name: str

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
    ) -> SearchResult: ...


class FlightStatusProvider(Protocol):
    name: str

    async def flight_status(self, flight_number: str) -> StatusResult: ...

    async def route_departures(
        self, origin: str, destination: str, airline: str | None = None
    ) -> StatusResult: ...


class CachedHTTP:
    """GET with: cache lookup -> budget check -> request -> record call -> cache."""

    def __init__(
        self,
        provider: str,
        base_url: str,
        store: Store,
        monthly_budget: int,
        stop_ratio: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url
        self.store = store
        self.monthly_budget = monthly_budget
        self.stop_ratio = stop_ratio
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0))

    async def get_json(
        self, path: str, params: dict[str, Any], ttl: int
    ) -> tuple[dict[str, Any], bool]:
        """Returns (json, was_cached)."""
        key = Store.make_key(self.provider, path, params)
        hit = self.store.get(key)
        if hit is not None:
            return hit, True

        self.store.check_budget(self.provider, self.monthly_budget, self.stop_ratio)
        try:
            resp = await self._client.get(self.base_url + path, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.provider}: network error: {exc.__class__.__name__}") from exc
        # The request reached the API, so it may have been billed — count it.
        self.store.record_call(self.provider)

        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"{self.provider}: HTTP {resp.status_code}, non-JSON body") from exc
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", f"HTTP {resp.status_code}")
            if isinstance(err, dict):
                err = err.get("message") or err.get("code") or str(err)
            raise ProviderError(f"{self.provider}: {err}")

        data["_fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.store.set(key, data, ttl)
        return data, False

    async def aclose(self) -> None:
        await self._client.aclose()
