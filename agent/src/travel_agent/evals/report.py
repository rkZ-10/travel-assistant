"""Markdown + JSON reports for an eval run."""
from __future__ import annotations

from collections import defaultdict

from .runner import EvalRun


def _pct(n: int, d: int) -> str:
    return f"{(100 * n / d):.0f}%" if d else "n/a"


def markdown(run: EvalRun) -> str:
    rs = run.results
    by_case: dict[str, list] = defaultdict(list)
    for r in rs:
        by_case[r.case_id].append(r)
    case_pass = sum(all(x.passed for x in v) for v in by_case.values())
    costs = [r.cost_usd for r in rs if r.cost_usd is not None]
    durs = [r.duration_ms for r in rs if r.duration_ms]
    lines = [
        f"# Eval run {run.started_at} · model `{run.model}`",
        "",
        f"- Cases passing (all attempts): **{case_pass}/{len(by_case)}** ({_pct(case_pass, len(by_case))})",
        f"- Attempts passing: {sum(r.passed for r in rs)}/{len(rs)}",
        f"- Estimated cost: ${sum(costs):.3f} total, ${(sum(costs) / len(costs)) if costs else 0:.3f}/attempt "
        "(an API-price estimate; on a Claude plan login this counts against plan usage instead)",
        f"- Median duration: {sorted(durs)[len(durs) // 2] / 1000:.1f}s" if durs else "- Duration: n/a",
        "",
    ]
    tags: dict[str, list[bool]] = defaultdict(list)
    for r in rs:
        for t in r.tags:
            tags[t].append(r.passed)
    if tags:
        lines += ["| Tag | Pass |", "|---|---|"]
        lines += [f"| {t} | {sum(v)}/{len(v)} |" for t, v in sorted(tags.items())]
        lines.append("")
    lines += ["| Case | Result | Failed checks | Tools | Turns | Est. cost |", "|---|---|---|---|---|---|"]
    for r in rs:
        failed = "<br>".join(f"`{c.name}`: {c.detail[:120]}" for c in r.failed) or "—"
        cost = f"${r.cost_usd:.3f}" if r.cost_usd is not None else "—"
        lines.append(
            f"| {r.case_id}#{r.attempt} | {'✅' if r.passed else '❌'} | {failed} | "
            f"{', '.join(r.tools) or '—'} | {r.turns or '—'} | {cost} |"
        )
    return "\n".join(lines) + "\n"


def write(run: EvalRun) -> None:
    assert run.out_dir
    (run.out_dir / "results.json").write_text(run.to_json(), encoding="utf-8")
    (run.out_dir / "summary.md").write_text(markdown(run), encoding="utf-8")
