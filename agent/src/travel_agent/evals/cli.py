"""travel-eval: run the eval suite against the live agent and write a report."""
from __future__ import annotations

import argparse
import asyncio
import sys

from ..config import AgentConfig
from .cases import load_cases
from .report import markdown, write
from .runner import RESULTS_DIR, rescore, run_eval

DEFAULT_SKIP_TAGS = {"quota-heavy"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="travel-eval")
    ap.add_argument("--only", nargs="+", metavar="ID", help="run only these case ids")
    ap.add_argument("--tags", nargs="+", help="run only cases with any of these tags")
    ap.add_argument("--include-heavy", action="store_true", help="also run quota-heavy cases")
    ap.add_argument("--model", default="sonnet", help="sonnet (default), haiku for cheap practice runs")
    ap.add_argument("--repeat", type=int, default=1, help="attempts per case (checks consistency)")
    ap.add_argument("--list", action="store_true", help="list cases and exit")
    ap.add_argument("--rescore", metavar="RUN_DIR",
                    help="re-check a finished run's saved traces (no agent calls); name or path under evals/results")
    args = ap.parse_args(argv)

    if args.rescore:
        from pathlib import Path

        run_dir = Path(args.rescore)
        run_dir = run_dir if run_dir.is_dir() else RESULTS_DIR / args.rescore
        run = rescore(run_dir, load_cases())
        write(run, suffix="-rescored")
        print(markdown(run))
        print(f"Report: {run_dir / 'summary-rescored.md'}")
        return 0 if all(r.passed for r in run.results) else 1

    cases = load_cases()
    if args.only:
        cases = [c for c in cases if c.id in set(args.only)]
    if args.tags:
        cases = [c for c in cases if set(c.tags) & set(args.tags)]
    if not (args.include_heavy or args.only):
        cases = [c for c in cases if not set(c.tags) & DEFAULT_SKIP_TAGS]
    if args.list:
        for c in cases:
            print(f"{c.id:<32} {','.join(c.tags):<28} {c.why}")
        return 0
    if not cases:
        print("No cases selected.")
        return 1

    cfg = AgentConfig.load(model=args.model)
    print(f"Running {len(cases)} case(s) x{args.repeat} with model {cfg.model}")
    run = asyncio.run(run_eval(cases, cfg, args.repeat))
    write(run)
    print("\n" + markdown(run))
    print(f"Report: {run.out_dir / 'summary.md'}")
    return 0 if all(r.passed for r in run.results) else 1


if __name__ == "__main__":
    sys.exit(main())
