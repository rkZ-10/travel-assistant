from datetime import date

import pytest

from travel_agent.evals import runner as eval_runner
from travel_agent.evals.cases import Case, Checks, load_cases, render
from travel_agent.evals.checks import run_checks, ungrounded_amounts
from travel_agent.evals.report import markdown
from travel_agent.trace import RunTrace, ToolCall

TODAY = date(2026, 10, 3)


def trace(answer, calls=(), denied=(), error=None):
    t = RunTrace(prompt="p", model="m", answer=answer, error=error)
    for i, (tool, inp, out) in enumerate(calls):
        t.tool_calls.append(ToolCall(id=f"t{i}", tool=tool, input=inp, result_text=out))
    t.denied = [{"tool": f"mcp__travel__{d}", "reason": "x"} for d in denied]
    return t


FLIGHTS = '{"itineraries":[{"price":6839,"segments":[{"flight_number":"IX 1831"}]},{"price":7069}]}'
POLICY = '{"passages":[{"text":"| Saver | 3499 | 4999 | 4299 |","fetched_on":"2026-10-01"}]}'


def test_render_dates():
    assert render("on {date+14}", TODAY) == "on Saturday 17 October 2026"
    assert render({"date": "{iso+14}"}, TODAY) == {"date": "2026-10-17"}


def test_cases_file_valid():
    cases = load_cases()
    assert len(cases) >= 15
    for c in cases:
        c.rendered(TODAY)  # placeholders render


def test_grounding_allows_quoted_difference_only():
    t = trace("IX 1831 is ₹6,839; 6E is ₹7,069, so ₹230 more. Fee ₹4,999.",
              [("search_flights", {}, FLIGHTS), ("search_policies", {}, POLICY)])
    assert ungrounded_amounts(t) == []
    t2 = trace("Refund would be ₹2,281.", [("search_flights", {}, FLIGHTS), ("search_policies", {}, POLICY)])
    assert ungrounded_amounts(t2) == [2281]  # 6839 - 4558 isn't allowed: those weren't quoted


def test_checks_pass_and_fail():
    checks = Checks(
        first_tool="get_travel_preferences",
        tools_include=["search_flights"],
        max_calls={"search_flights": 1},
        tool_args=[{"tool": "search_flights", "args": {"origin": "hyd", "nonstop_only": True}},
                   {"tool": "search_policies", "args": {"airlines": {"contains": "DGCA"}}}],
        answer_matches=["4,?999"],
        cites_policy_date=True,
        grounded_amounts=True,
    )
    good = trace("Fee ₹4,999 (IndiGo, fetched 2026-10-01). Fare ₹6,839.", [
        ("get_travel_preferences", {}, "{}"),
        ("search_flights", {"origin": "HYD", "nonstop_only": True}, FLIGHTS),
        ("search_policies", {"airlines": ["dgca"]}, POLICY),
    ])
    assert all(c.passed for c in run_checks(checks, good))

    bad = trace("Fee ₹3,000.", [("search_flights", {"origin": "BLR"}, FLIGHTS), ("search_flights", {}, FLIGHTS)])
    failed = {c.name.split(":")[0] for c in run_checks(checks, bad) if not c.passed}
    assert {"first", "max_calls", "args", "answer~/4,?999/", "cites_policy_date", "grounded_amounts"} <= failed


def test_asks_question_and_denied():
    c = Checks(asks_question=True, denied=["update_travel_preferences"])
    ok = trace("Which date do you want to fly?", [("update_travel_preferences", {}, "")], denied=["update_travel_preferences"])
    assert all(r.passed for r in run_checks(c, ok))
    searched = trace("Which date?", [("search_flights", {}, FLIGHTS)])
    assert not run_checks(Checks(asks_question=True), searched)[1].passed


def test_error_fails_case():
    assert not run_checks(Checks(), trace("", error="max_turns: x"))[0].passed


async def test_run_case_isolates_prefs_and_scores(monkeypatch, tmp_path):
    seen = {}

    async def fake_ask_once(prompt, cfg, approver):
        import json
        from pathlib import Path

        prefs = Path(cfg.mcp_env["TRAVEL_MCP_PREFS_DIR"]) / "preferences.json"
        seen["prefs"] = json.loads(prefs.read_text())
        seen["ttl"] = cfg.mcp_env["TRAVEL_MCP_SEARCH_TTL"]
        seen["prompt"] = prompt
        seen["approver"] = approver
        return trace("Which date?", [("get_travel_preferences", {}, "{}")])

    monkeypatch.setattr(eval_runner, "ask_once", fake_ask_once)
    case = Case(id="c1", prompt="fly on {date+1}", preferences={"home_airport": "HYD"},
                checks=Checks(asks_question=True))
    from travel_agent.config import AgentConfig

    r = await eval_runner.run_case(case, AgentConfig(), tmp_path)
    assert r.passed and seen["prefs"] == {"home_airport": "HYD"} and seen["ttl"] == "86400"
    assert "{date" not in seen["prompt"] and seen["approver"] is not eval_runner.approve_all

    run = eval_runner.EvalRun(started_at="x", model="haiku", results=[r])
    md = markdown(run)
    assert "1/1" in md and "c1#1" in md
