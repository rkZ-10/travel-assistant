from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from travel_mcp.cache import Store
from travel_mcp.config import Settings
from travel_mcp.providers.airlabs import AirLabsStatusProvider
from travel_mcp.providers.base import CachedHTTP
from travel_mcp.providers.serpapi import GoogleFlightsProvider
from travel_mcp.server import Services

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Recorder:
    """httpx transport that serves a fixture and records requests made."""

    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.payload)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(serpapi_key="test-serp", airlabs_key="test-air", data_dir=tmp_path)


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def make_services(settings: Settings, store: Store, serp: Recorder, air: Recorder) -> Services:
    serp_http = CachedHTTP(
        "serpapi", "https://serpapi.com", store, settings.serpapi_monthly_budget,
        settings.budget_stop_ratio, httpx.AsyncClient(transport=httpx.MockTransport(serp)),
    )
    air_http = CachedHTTP(
        "airlabs", "https://airlabs.co/api/v9", store, settings.airlabs_monthly_budget,
        settings.budget_stop_ratio, httpx.AsyncClient(transport=httpx.MockTransport(air)),
    )
    return Services(
        settings=settings,
        store=store,
        search=GoogleFlightsProvider(settings.serpapi_key, serp_http, settings.search_ttl),
        status=AirLabsStatusProvider(settings.airlabs_key, air_http, settings.status_ttl),
    )
