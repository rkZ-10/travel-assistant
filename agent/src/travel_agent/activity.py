"""Human-readable labels for tool calls, shown live in the CLI and web UI."""
from __future__ import annotations

from typing import Any

AIRLINES = {"6E": "IndiGo", "AI": "Air India", "IX": "Air India Express", "QP": "Akasa", "SG": "SpiceJet",
            "9I": "Alliance Air", "DGCA": "DGCA rules"}


def _airlines(codes: Any) -> str:
    if not codes:
        return ""
    return ", ".join(AIRLINES.get(str(c).upper(), str(c).upper()) for c in codes)


def label(tool: str, args: dict[str, Any] | None) -> str:
    a = args or {}
    if tool == "search_flights":
        route = f"{a.get('origin', '?')} → {a.get('destination', '?')}"
        when = a.get("date", "")
        if a.get("return_date"):
            when += f", back {a['return_date']}"
        extras = [x for x in (
            "nonstop" if a.get("nonstop_only") else "",
            f"under ₹{a['max_price']:,}" if isinstance(a.get("max_price"), int) else "",
            _airlines(a.get("airlines")),
        ) if x]
        return f"Searching flights {route} on {when}" + (f" ({', '.join(extras)})" if extras else "")
    if tool == "search_policies":
        who = _airlines(a.get("airlines"))
        return f"Checking fare rules{': ' + who if who else ''}"
    if tool == "get_travel_preferences":
        return "Reading your preferences"
    if tool == "update_travel_preferences":
        return "Saving a preference"
    if tool == "get_flight_status":
        return f"Checking status of {a.get('flight_number', 'flight')}"
    if tool == "get_route_departures":
        return f"Checking departures {a.get('origin', '?')} → {a.get('destination', '?')}"
    if tool == "list_policy_sources":
        return "Listing policy sources"
    if tool == "get_api_usage":
        return "Checking API usage"
    if tool == "show_flight_cards":
        n = len(a.get("flights") or [])
        return f"Showing {n} flight card{'s' if n != 1 else ''}"
    return tool.replace("_", " ").capitalize()
