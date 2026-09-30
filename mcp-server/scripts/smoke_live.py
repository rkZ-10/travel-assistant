"""Live smoke test: 1 SerpApi search + 1 AirLabs route lookup (2 real API calls).

    uv run python scripts/smoke_live.py            # print a summary
    uv run python scripts/smoke_live.py --record   # also save raw responses as test fixtures
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from travel_mcp.cache import Store
from travel_mcp.config import Settings
from travel_mcp.providers.airlabs import AirLabsStatusProvider
from travel_mcp.providers.base import CachedHTTP
from travel_mcp.providers.serpapi import GoogleFlightsProvider
from travel_mcp.server import IST

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SECRET_KEYS = {"api_key", "key"}


def scrub(obj):
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in SECRET_KEYS else scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


async def main(record: bool, origin: str, destination: str, days: int) -> None:
    s = Settings.load()
    store = Store(s.data_dir / "travel_mcp.sqlite3")
    captured: dict[str, dict] = {}

    async def capture(resp: httpx.Response) -> None:
        await resp.aread()
        host = resp.request.url.host
        captured[host] = resp.json()

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=45, event_hooks={"response": [capture]})

    serp = GoogleFlightsProvider(
        s.serpapi_key,
        CachedHTTP("serpapi", "https://serpapi.com", store, s.serpapi_monthly_budget, s.budget_stop_ratio, client()),
        s.search_ttl,
    )
    air = AirLabsStatusProvider(
        s.airlabs_key,
        CachedHTTP("airlabs", "https://airlabs.co/api/v9", store, s.airlabs_monthly_budget, s.budget_stop_ratio, client()),
        s.status_ttl,
    )

    date = (datetime.now(IST).date() + timedelta(days=days)).isoformat()
    print(f"== search_flights {origin}->{destination} on {date}")
    res = await serp.search(origin, destination, date)
    print(f"   {res.total_found} itineraries (cached={res.cached}); price level: "
          f"{res.price_insights.price_level if res.price_insights else 'n/a'}")
    for it in res.itineraries[:5]:
        seg = it.segments[0]
        print(f"   INR {str(it.price or '-'):>7}  {seg.flight_number:<8} {seg.departs[-5:]}  "
              f"{it.stops} stop(s)  {it.total_duration_min} min")

    print(f"== get_route_departures {origin}->{destination} (next ~12h)")
    st = await air.route_departures(origin, destination)
    print(f"   {len(st.flights)} operating flights (cached={st.cached})")
    for f in st.flights[:5]:
        print(f"   {f.flight_number:<7} {f.scheduled_departure[-5:]}  {f.status:<10} "
              f"delay={f.departure_delay_min}  +{len(f.marketed_as)} codeshares")

    if record:
        for host, name in [("serpapi.com", f"serpapi_google_flights_{origin}_{destination}.json"),
                           ("airlabs.co", f"airlabs_schedules_{origin}_{destination}.live.json")]:
            if host in captured:
                path = FIXTURES / name
                path.write_text(json.dumps(scrub(captured[host]), indent=1), encoding="utf-8")
                print(f"   recorded {path.name}")
        if not captured:
            print("   nothing recorded (both responses came from local cache)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--origin", default="DEL")
    ap.add_argument("--destination", default="BOM")
    ap.add_argument("--days", type=int, default=14, help="search this many days ahead")
    a = ap.parse_args()
    asyncio.run(main(a.record, a.origin.upper(), a.destination.upper(), a.days))
