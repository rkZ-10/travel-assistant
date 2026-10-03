"""Deterministic checks over a RunTrace. Each returns (passed, detail)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..trace import RunTrace
from .cases import Checks

_AMOUNT = re.compile(r"(?:₹|INR|Rs\.?)\s?(\d[\d,]*(?:\.\d+)?)", re.I)
_NUMBER = re.compile(r"\d[\d,]*")
_ISO_DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def _norm(n: str) -> int | None:
    try:
        return int(float(n.replace(",", "")))
    except ValueError:
        return None


def tool_numbers(trace: RunTrace) -> set[int]:
    nums: set[int] = set()
    for c in trace.tool_calls:
        for m in _NUMBER.findall(c.result_text):
            if (v := _norm(m)) is not None:
                nums.add(v)
    return nums


def answer_amounts(answer: str) -> list[int]:
    return [v for m in _AMOUNT.findall(answer) if (v := _norm(m)) is not None and v >= 100]


def ungrounded_amounts(trace: RunTrace) -> list[int]:
    """₹ amounts in the answer that no tool returned.

    A derived figure is allowed only when it's the difference or sum of two *other grounded
    amounts quoted in the same answer* (e.g. "₹230 more" next to ₹6,839 and ₹7,069). Allowing any
    pair of tool numbers would excuse almost anything, given how many numbers a search returns."""
    known = tool_numbers(trace)
    amounts = answer_amounts(trace.answer)
    grounded = {v for v in amounts if v in known}
    bad = []
    for v in amounts:
        if v in grounded:
            continue
        # v = a - b, v = b - a, or v = a + b
        if not any({a - v, a + v, v - a} & grounded for a in grounded):
            bad.append(v)
    return sorted(set(bad))


def _matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        if "present" in expected:
            return (actual is not None) == bool(expected["present"])
        if "contains" in expected:
            items = actual or []
            items = [str(i).upper() for i in items] if isinstance(items, list) else [str(items).upper()]
            return str(expected["contains"]).upper() in items
        if "max" in expected:
            return actual is not None and actual <= expected["max"]
        raise ValueError(f"unknown matcher {expected}")
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().upper() == actual.strip().upper()
    return expected == actual


def run_checks(checks: Checks, trace: RunTrace) -> list[CheckResult]:
    out: list[CheckResult] = []
    used = trace.tools_used

    def add(name: str, ok: bool, detail: str = "") -> None:
        out.append(CheckResult(name, ok, "" if ok else detail))

    add("no_error", not trace.error, trace.error or "")
    for t in checks.tools_include:
        add(f"uses:{t}", t in used, f"tools used: {used}")
    for t in checks.tools_exclude:
        add(f"avoids:{t}", t not in used, f"{t} was called")
    if checks.first_tool:
        add(f"first:{checks.first_tool}", bool(used) and used[0] == checks.first_tool, f"first was {used[:1]}")
    for t, n in checks.max_calls.items():
        add(f"max_calls:{t}<={n}", used.count(t) <= n, f"{used.count(t)} calls")
    for ta in checks.tool_args:
        calls = [c.input for c in trace.tool_calls if c.tool == ta.tool]
        ok = any(all(_matches(v, args.get(k)) for k, v in ta.args.items()) for args in calls)
        add(f"args:{ta.tool}{json.dumps(ta.args, ensure_ascii=False)}", ok, f"calls: {calls}")
    denied_tools = [d["tool"].split("__")[-1] for d in trace.denied]
    for t in checks.denied:
        add(f"denied:{t}", t in denied_tools, f"denied: {denied_tools}")
    for rx in checks.answer_matches:
        add(f"answer~/{rx}/", bool(re.search(rx, trace.answer, re.I | re.S)), "pattern not found in answer")
    for rx in checks.answer_not_matches:
        add(f"answer!~/{rx}/", not re.search(rx, trace.answer, re.I | re.S), "forbidden pattern found")
    if checks.asks_question:
        add("asks_question", "?" in trace.answer and "search_flights" not in used,
            "no question asked, or searched without the missing info")
    if checks.cites_policy_date:
        dates = {d for c in trace.tool_calls if c.tool == "search_policies" for d in _ISO_DATE.findall(c.result_text)}
        add("cites_policy_date", any(d in trace.answer for d in dates), f"policy dates {sorted(dates)} not in answer")
    if checks.grounded_amounts:
        bad = ungrounded_amounts(trace)
        add("grounded_amounts", not bad, f"amounts not found in any tool result: {bad}")
    return out
