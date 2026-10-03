import json

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage

from travel_agent.trace import RunTrace


def run_messages():
    return [
        AssistantMessage(content=[ToolUseBlock("t1", "mcp__travel__get_travel_preferences", {})], model="m"),
        UserMessage(content=[ToolResultBlock("t1", [{"type": "text", "text": '{"home_airport":"HYD"}'}], False)]),
        AssistantMessage(content=[
            TextBlock("Searching…"),
            ToolUseBlock("t2", "mcp__travel__search_flights", {"origin": "HYD", "destination": "MAA", "date": "2026-10-14"}),
        ], model="m"),
        UserMessage(content=[ToolResultBlock("t2", "x" * 1000, True)]),
        AssistantMessage(content=[TextBlock("Take IX 1831.")], model="m"),
        ResultMessage(subtype="success", duration_ms=4200, duration_api_ms=3000, is_error=False, num_turns=3,
                      session_id="s1", total_cost_usd=0.0123, usage={"input_tokens": 10}, result="Take IX 1831."),
    ]


def test_trace_collects_calls_results_and_cost(tmp_path):
    t = RunTrace(prompt="HYD to MAA Oct 14", model="sonnet")
    for m in run_messages():
        t.add(m)
    assert t.tools_used == ["get_travel_preferences", "search_flights"]
    assert t.tool_calls[0].result_preview == '{"home_airport":"HYD"}'
    assert t.tool_calls[1].is_error is True and t.tool_calls[1].result_preview.endswith("…")
    assert len(t.tool_calls[1].result_text) == 1000
    assert t.answer == "Take IX 1831." and t.cost_usd == 0.0123 and t.turns == 3
    path = t.save(tmp_path)
    data = json.loads(path.read_text())
    assert data["tool_calls"][1]["input"]["destination"] == "MAA" and "started" not in data["tool_calls"][0]
    assert t.save(tmp_path) != path  # no overwrite within the same second


def test_error_result_recorded():
    t = RunTrace(prompt="x", model="m")
    t.add(ResultMessage(subtype="error_max_budget_usd", duration_ms=1, duration_api_ms=1, is_error=True,
                        num_turns=9, session_id="s"))
    assert t.error.startswith("error_max_budget_usd")


async def test_timer_measures_between_hooks():
    import asyncio

    from travel_agent.trace import ToolTimer

    timer = ToolTimer()
    await timer.pre({}, "t1", None)
    await asyncio.sleep(0.02)
    await timer.post({}, "t1", None)
    await timer.post({}, "unknown", None)  # no matching pre: ignored
    t = RunTrace(prompt="x", model="m")
    for m in run_messages():
        t.add(m)
    t.apply_timings(timer.durations_ms)
    assert t.tool_calls[0].duration_ms >= 15


def test_error_reported_with_success_subtype():
    t = RunTrace(prompt="x", model="m")
    t.add(AssistantMessage(content=[TextBlock("Failed to refresh OAuth token: ...")], model="m"))
    t.add(ResultMessage(subtype="success", duration_ms=1, duration_api_ms=0, is_error=True, num_turns=1,
                        session_id="s", result="Failed to refresh OAuth token: another process"))
    assert "OAuth" in t.error and t.answer == ""
