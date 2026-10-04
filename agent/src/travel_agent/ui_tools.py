"""Display-only tools for the web UI, served in-process (Claude Agent SDK MCP server "ui").

show_flight_cards: the agent picks which itineraries to show (by flight number, or booking token)
and adds a short label/note. Every fact on a card (airline, times, price, booking token) is filled in
from the actual search_flights result. The agent can't put a wrong price or an invented booking link
on a card: flights that aren't in this conversation's results are rejected. Booking links themselves are fetched only when the user clicks.
"""
from __future__ import annotations

import json
import re
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


def _norm_flights(text: str) -> str:
    """'6E 243 + 6E-500' -> '6E243,6E500' so flight numbers compare regardless of spacing."""
    return ",".join(a + n for a, n in re.findall(r"\b([A-Z0-9]{2})[\s-]?(\d{1,4})\b", text.upper()))


class SearchRegistry:
    """Itineraries seen in this session's search_flights results, keyed by booking_token."""

    def __init__(self) -> None:
        self.by_token: dict[str, dict[str, Any]] = {}

    def find(self, booking_token: str = "", flight: str = "") -> tuple[str, dict[str, Any]] | None:
        """Look up by exact booking_token, else by flight number(s) (latest search wins).

        Booking tokens are long opaque strings and models occasionally mangle them when copying,
        while flight numbers are short and also unique within one search."""
        token = booking_token.strip()
        if token in self.by_token:
            return token, self.by_token[token]
        want = _norm_flights(flight)
        if not want:
            return None
        for tok, entry in reversed(self.by_token.items()):
            segs = entry["itinerary"].get("segments") or []
            if _norm_flights(" ".join(str(x.get("flight_number", "")) for x in segs)) == want:
                return tok, entry
        return None

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
        "Identify each itinerary by its flight number(s) as search_flights returned them (e.g. '6E 243', "
        "or '6E 243, 6E 512' for a connection); booking_token also works if copied exactly. Add a short label "
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
                            "flight": {"type": "string", "description": "flight number(s), e.g. '6E 243'"},
                            "booking_token": {"type": "string"},
                            "label": {"type": "string", "maxLength": 40},
                            "note": {"type": "string", "maxLength": 240},
                        },
                    },
                }
            },
            "required": ["flights"],
        },
    )
    async def show_flight_cards(args: dict[str, Any]) -> dict[str, Any]:
        cards, unknown = [], []
        for f in args.get("flights") or []:
            found = registry.find(str(f.get("booking_token") or ""), str(f.get("flight") or ""))
            if not found:
                unknown.append(f.get("flight") or f.get("label") or "unlabelled")
                continue
            token, entry = found
            if any(c["booking_token"] == token for c in cards):
                continue
            cards.append({**entry, "label": f.get("label"), "note": f.get("note"), "booking_token": token})
        if not cards:
            return {"content": [{"type": "text", "text":
                    "No cards shown: none of those flights came from a search_flights result in this "
                    "conversation. Use flight numbers exactly as the itineraries list them."}], "is_error": True}
        result = emit({"type": "flight_cards", "cards": cards})
        if hasattr(result, "__await__"):
            await result
        msg = (f"Showed {len(cards)} card(s). The user can click 'See booking options' to get airline/"
               "travel-site links; don't write booking URLs yourself.")
        if unknown:
            msg += f" Skipped (not in this conversation's search results): {', '.join(unknown)}."
        return {"content": [{"type": "text", "text": msg}]}

    return create_sdk_mcp_server(UI_SERVER, tools=[show_flight_cards]), show_flight_cards
