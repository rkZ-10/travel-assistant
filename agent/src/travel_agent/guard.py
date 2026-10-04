"""Guardrails, enforced in code (PreToolUse hook) rather than trusted to the prompt:

- only travel tools may run
- a per-request cap on live flight searches (SerpApi quota)
- every preference write needs the user's approval (human in the loop, the same pattern booking
  will use later)
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .config import TRAVEL_TOOLS, bare_name

# Server tools the agent must not call, with the reason it's told.
AGENT_DENIED = {
    "get_booking_options": "Booking links are fetched by the UI only when the user clicks 'See booking options' "
    "(each lookup costs quota). Use show_flight_cards to offer them.",
}

Approver = Callable[[str, dict[str, Any]], Awaitable[bool]]


async def deny_all(_tool: str, _input: dict[str, Any]) -> bool:
    return False


@dataclass
class Decision:
    allow: bool
    reason: str = ""


@dataclass
class ToolGuard:
    max_flight_searches: int = 4
    approver: Approver = deny_all
    ui_tools: frozenset[str] = frozenset()  # e.g. {"mcp__ui__show_flight_cards"} in web mode
    searches: int = 0
    seen_searches: set[str] = field(default_factory=set)
    denied: list[dict[str, Any]] = field(default_factory=list)

    def reset(self) -> None:
        """Call at the start of each user request (budgets are per request)."""
        self.searches = 0
        self.seen_searches.clear()

    async def decide(self, tool_name: str, tool_input: dict[str, Any]) -> Decision:
        if tool_name in self.ui_tools:
            return Decision(True)
        tool = bare_name(tool_name)
        if tool in AGENT_DENIED and tool_name != tool:
            return self._deny(tool_name, AGENT_DENIED[tool])
        if tool not in TRAVEL_TOOLS or tool_name == tool:
            return self._deny(tool_name, "Only the travel tools are available to this assistant.")

        if tool == "search_flights":
            key = json.dumps(tool_input, sort_keys=True)
            if key in self.seen_searches:  # identical repeat: served from cache, but pointless
                return self._deny(tool_name, "You already ran this exact search; reuse its results.")
            if self.searches >= self.max_flight_searches:
                return self._deny(
                    tool_name,
                    f"Search limit for this request reached ({self.max_flight_searches}). Work with "
                    "the results you have, or ask the user to narrow the request.",
                )
            self.searches += 1
            self.seen_searches.add(key)

        if tool == "update_travel_preferences":
            if not await self.approver(tool, tool_input):
                return self._deny(
                    tool_name,
                    "The user did not approve saving this preference. Tell them it was not saved.",
                )
        return Decision(True)

    def _deny(self, tool_name: str, reason: str) -> Decision:
        self.denied.append({"tool": tool_name, "reason": reason})
        return Decision(False, reason)

    async def hook(self, hook_input: dict[str, Any], _tool_use_id: str | None, _ctx: Any) -> dict:
        """PreToolUse hook callback for ClaudeAgentOptions.hooks."""
        d = await self.decide(hook_input.get("tool_name", ""), hook_input.get("tool_input") or {})
        if d.allow:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": d.reason,
            }
        }
