"""Check what Google Flights offers as booking options on a route (2 real SerpApi searches).

    python -m uv run python scripts/probe_booking.py                  # HYD -> MAA, 14 days out
    python -m uv run python scripts/probe_booking.py --origin DEL --destination BOM --days 10 --record

Prints, for the cheapest few itineraries' first one: each seller, whether it's airline-direct,
fare type, price, and whether a redirect link came back. --record saves the response as a test
fixture (redirect form data truncated).
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from travel_mcp.server import IST, build_services

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


async def main(origin: str, destination: str, days: int, record: bool) -> None:
    svc = build_services()
    date = (datetime.now(IST).date() + timedelta(days=days)).isoformat()
    res = await svc.search.search(origin, destination, date, nonstop_only=True, limit=3)
    print(f"== {origin}->{destination} {date}: {res.total_found} itineraries (fetched {res.fetched_at})")
    if not res.itineraries:
        print("   no itineraries")
        return
    it = res.itineraries[0]
    print(f"   probing {it.segments[0].flight_number} at INR {it.price}")
    if not it.booking_token:
        print("   no booking_token on this itinerary")
        return
    opts = await svc.search.booking_options(it.booking_token, origin, destination, date)
    for n in opts.notes:
        print(f"   NOTE: {n}")
    for o in opts.options:
        link = "link" if o.booking_url and o.booking_post_data else ("phone" if o.booking_phone else "no link")
        print(f"   {o.seller:<22} {'AIRLINE' if o.is_airline else 'site   '} {str(o.fare_name or '-'):<14} "
              f"INR {str(o.price or '-'):>7}  {link}")
    if record:
        data = opts.model_dump()
        for o in data["options"]:
            if o.get("booking_post_data"):
                o["booking_post_data"] = o["booking_post_data"][:40] + "…"
        path = FIXTURES / f"serpapi_booking_options_{origin}_{destination}.json"
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"   recorded {path.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", default="HYD")
    ap.add_argument("--destination", default="MAA")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.origin.upper(), a.destination.upper(), a.days, a.record))
