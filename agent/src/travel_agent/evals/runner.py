"""Run eval cases through the real agent, each with its own preferences, and score them."""
from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import REPO_ROOT, AgentConfig
from ..guard import deny_all
from ..runner import ask_once
from ..trace import RunTrace
from .cases import Case
from .checks import CheckResult, run_checks

RESULTS_DIR = REPO_ROOT / "evals" / "results"
PINNED_SEARCH_TTL = 24 * 3600  # same flight results for a day: repeat runs are free and comparable


async def approve_all(_tool, _input) -> bool:
    return True


@dataclass
class CaseResult:
    case_id: str
    tags: list[str]
    attempt: int
    passed: bool
    checks: list[CheckResult]
    tools: list[str]
    turns: int | None
    cost_usd: float | None
    duration_ms: int | None
    answer: str
    error: str | None = None

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


@dataclass
class EvalRun:
    started_at: str
    model: str
    results: list[CaseResult] = field(default_factory=list)
    out_dir: Path | None = None

    def to_json(self) -> str:
        d = {"started_at": self.started_at, "model": self.model,
             "results": [asdict(r) for r in self.results]}
        return json.dumps(d, indent=2, ensure_ascii=False)


async def run_case(case: Case, cfg: AgentConfig, out_dir: Path, attempt: int = 1) -> CaseResult:
    case = case.rendered()
    with tempfile.TemporaryDirectory(prefix=f"eval-{case.id}-") as prefs_dir:
        if case.preferences:
            (Path(prefs_dir) / "preferences.json").write_text(json.dumps(case.preferences), encoding="utf-8")
        cfg.mcp_env = {"TRAVEL_MCP_PREFS_DIR": prefs_dir, "TRAVEL_MCP_SEARCH_TTL": str(PINNED_SEARCH_TTL)}
        cfg.runs_dir = out_dir / "traces" / f"{case.id}-{attempt}"
        cfg.ui = case.ui
        approver = approve_all if case.approve_preference_writes else deny_all
        try:
            trace = await ask_once(case.prompt, cfg, approver)
        except Exception as exc:  # noqa: BLE001 - a crashed case is a failed case, keep going
            trace = RunTrace(prompt=case.prompt, model=cfg.model, error=f"{type(exc).__name__}: {exc}")
    checks = run_checks(case.checks, trace)
    return CaseResult(
        case_id=case.id, tags=case.tags, attempt=attempt, passed=all(c.passed for c in checks),
        checks=checks, tools=trace.tools_used, turns=trace.turns, cost_usd=trace.cost_usd,
        duration_ms=trace.duration_ms, answer=trace.answer, error=trace.error,
    )


def rescore(run_dir: Path, cases: list[Case]) -> EvalRun:
    """Re-run the checks on a finished run's saved traces (after fixing a check or case),
    without calling the agent again."""
    import re as _re

    prev = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    by_id = {c.id: c for c in cases}
    started = datetime.strptime(prev["started_at"], "%Y%m%d-%H%M%S").date()
    run = EvalRun(started_at=prev["started_at"] + "-rescored", model=prev["model"], out_dir=run_dir)
    for trace_dir in sorted((run_dir / "traces").iterdir()):
        m = _re.match(r"(.+)-(\d+)$", trace_dir.name)
        files = sorted(trace_dir.glob("*.json"))
        if not (m and files and m.group(1) in by_id):
            continue
        case = by_id[m.group(1)].rendered(started)  # dates as of the original run
        trace = RunTrace.from_dict(json.loads(files[-1].read_text(encoding="utf-8")))
        checks = run_checks(case.checks, trace)
        run.results.append(CaseResult(
            case_id=case.id, tags=case.tags, attempt=int(m.group(2)), passed=all(c.passed for c in checks),
            checks=checks, tools=trace.tools_used, turns=trace.turns, cost_usd=trace.cost_usd,
            duration_ms=trace.duration_ms, answer=trace.answer, error=trace.error,
        ))
    order = {c.id: i for i, c in enumerate(cases)}
    run.results.sort(key=lambda r: (order.get(r.case_id, 999), r.attempt))
    return run


async def run_eval(cases: list[Case], cfg: AgentConfig, repeat: int = 1, progress=print) -> EvalRun:
    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    run = EvalRun(started_at=started, model=cfg.model, out_dir=RESULTS_DIR / f"{started}-{cfg.model}")
    run.out_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        for attempt in range(1, repeat + 1):
            progress(f"  {case.id} (attempt {attempt}/{repeat}) ...")
            r = await run_case(case, cfg, run.out_dir, attempt)
            run.results.append(r)
            mark = "PASS" if r.passed else "FAIL"
            progress(f"    {mark}" + ("" if r.passed else "  " + "; ".join(c.name for c in r.failed)))
    return run
