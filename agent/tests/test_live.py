"""End-to-end against the real model + MCP server. Costs a few cents and 1 SerpApi search.

    $env:TRAVEL_AGENT_LIVE=1; python -m uv run pytest tests/test_live.py -s
"""
import os

import pytest

from travel_agent.config import AgentConfig
from travel_agent.runner import ask_once

pytestmark = pytest.mark.skipif(not os.getenv("TRAVEL_AGENT_LIVE"), reason="set TRAVEL_AGENT_LIVE=1")


async def test_trip_request_uses_prefs_search_and_policies():
    t = await ask_once(
        "Cheapest nonstop Hyderabad to Chennai two weeks from today, and what would it cost me to cancel?",
        AgentConfig.load(max_budget_usd=0.40),
    )
    print(t.answer)
    assert not t.error, t.error
    assert t.tools_used[0] == "get_travel_preferences"
    assert "search_flights" in t.tools_used and "search_policies" in t.tools_used
    assert "₹" in t.answer or "INR" in t.answer
