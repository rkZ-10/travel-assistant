"""Display-only tools for the web UI, served in-process (Claude Agent SDK MCP server "ui").

show_flight_cards: the agent picks which itineraries to show and adds a short label/note. Every
fact on a card (airline, times, price, booking token) is filled in from the actual search_flights
result. The agent can't put a wrong price or an invented booking link on a card: unknown tokens
are rejected. Booking links themselves are fetched only when the user clicks.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

UI_SERVER = "ui"
UI_TOOLS = ["show_flight_cards"]


def _texts(response: Any) -> list[str]:
    """Pull JSON-ish text out of whatever shape the SDK gives for an MCP tool response."""
    if isinstance(response, str):
        return [response]
    if isinstance(response, dict):
        if "itineraries" in response:
            return [json.dumps(response)]
        out = []
        for key in ("structuredContent", "structured_content"):
            if isinstance(response.get(key), dict):
                out.append(json.dumps(response[key]))
        content = response.get("content")
        if content is not None:
            out += _texts(content)
        return out
    if isinstance(response, list):
        out = []
        for item in response:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                out.append(item["text"])
            else:
                out += _texts(item)
        return out
    return []


class SearchRegistry:
    """Itineraries seen in this session's search_flights results, keyed by booking_token."""

    def __init__(self) -> None:
        self.by_token: dict[str, dict[str, Any]] = {}

    def record(self, tool_input: dict[str, Any], tool_response: Any) -> int:
        added = 0
        for text in _texts(tool_response):
            try:
                result = json.loads(text)
            except (TypeError, ValueError):
                continue
            if not isinstance(result, dict) or "itineraries" not in result:
                continue
            search = {k: result.get(k) or tool_input.get(k) for k in ("origin", "destination", "date", "return_date")}
            for it in result.get("itineraries") or []:
                token = it.get("booking_token")
                if token:
                    self.by_token[token] = {
                        "itinerary": it, "search": search, "currency": result.get("currency", "INR"),
                        "fetched_at": result.get("fetched_at"),
                        "links_valid_minutes": result.get("links_valid_minutes", 30),
                        "source_url": result.get("source_url"),
                    }
                    added += 1
        return added


def build_ui_server(registry: SearchRegistry, emit: Callable[[dict], Any]):
    @tool(
        "show_flight_cards",
        "Show 1-3 shortlisted flights to the user as cards with a 'See booking options' button. "
        "Pass each itinerary's booking_token exactly as search_flights returned it, plus a short label "
        "(e.g. 'Cheapest', 'Best timing') and a one-line note (e.g. the cancellation fee with its source). "
        "Airline, times and price are filled in from the search result automatically.",
        {
            "type": "object",
            "properties": {
                "flights": {
                    "type": "array", "minItems": 1, "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "booking_token": {"type": "string"},
                            "label": {"type": "string", "maxLength": 40},
                            "note": {"type": "string", "maxLength": 240},
                        },
                        "required": ["booking_token"],
                    },
                }
            },
            "required": ["flights"],
        },
    )
    async def show_flight_cards(args: dict[str, Any]) -> dict[str, Any]:
        cards, unknown = [], []
        for f in args.get("flights") or []:
            entry = registry.by_token.get(str(f.get("booking_token", "")).strip())
            if not entry:
                unknown.append(f.get("label") or "unlabelled")
                continue
            cards.append({**entry, "label": f.get("label"), "note": f.get("note"),
                          "booking_token": f["booking_token"]})
        if not cards:
            return {"content": [{"type": "text", "text":
                    "No cards shown: none of those booking_tokens came from a search_flights result in "
                    "this conversation. Copy booking_token exactly from the itineraries."}], "is_error": True}
        result = emit({"type": "flight_cards", "cards": cards})
        if hasattr(result, "__await__"):
            await result
        msg = (f"Showed {len(cards)} card(s). The user can click 'See booking options' to get airline/"
               "travel-site links; don't write booking URLs yourself.")
        if unknown:
            msg += f" Skipped (unknown booking_token): {', '.join(unknown)}."
        return {"content": [{"type": "text", "text": msg}]}

    return create_sdk_mcp_server(UI_SERVER, tools=[show_flight_cards]), show_flight_cards
