"""travel-agent: `ask` for one question, `chat` for a conversation."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from .config import AgentConfig
from .guard import deny_all
from .runner import ask_once, open_agent
from .trace import RunTrace


async def console_approver(tool: str, tool_input: dict[str, Any]) -> bool:
    changes = tool_input.get("changes", tool_input)
    print(f"\n[approval] The assistant wants to save preferences:\n{json.dumps(changes, indent=2)}")
    answer = await asyncio.to_thread(input, "Save these? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def _summary(t: RunTrace, verbose: bool) -> str:
    tools = ", ".join(t.tools_used) or "none"
    cost = f"${t.cost_usd:.4f}" if t.cost_usd is not None else "n/a"
    lines = [f"\n— tools: {tools} · turns: {t.turns} · cost: {cost}"]
    for d in t.denied:
        lines.append(f"  blocked {d['tool']}: {d['reason']}")
    if verbose:
        for c in t.tool_calls:
            flag = " ERROR" if c.is_error else ""
            lines.append(f"  {c.tool}({json.dumps(c.input, ensure_ascii=False)}) {c.duration_ms}ms{flag}")
    if t.error:
        lines.append(f"  run error: {t.error}")
    return "\n".join(lines)


async def _ask(args: argparse.Namespace) -> int:
    cfg = AgentConfig.load(model=args.model, max_budget_usd=args.budget)
    approver = console_approver if args.allow_pref_changes else deny_all
    trace = await ask_once(args.prompt, cfg, approver)
    if trace.answer:
        print(trace.answer)
    print(_summary(trace, args.verbose))
    if trace.error and "oauth" in trace.error.lower():
        print("  hint: another Claude Code/Desktop process kept refreshing the shared login (retried "
              "automatically). Try again in a minute, or close other Claude Code windows.")
    return 1 if trace.error else 0


async def _chat(args: argparse.Namespace) -> int:
    cfg = AgentConfig.load(model=args.model, max_budget_usd=args.budget)
    print("Travel assistant. Ask about flights, fares, baggage or status. Ctrl+C or 'exit' to quit.")
    async with open_agent(cfg, console_approver) as agent:
        while True:
            try:
                prompt = (await asyncio.to_thread(input, "\nyou> ")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if prompt.lower() in {"exit", "quit"}:
                break
            if not prompt:
                continue
            trace = await agent.ask(prompt)
            print("\nassistant> " + trace.answer)
            print(_summary(trace, args.verbose))
    return 0


def main(argv: list[str] | None = None) -> int:
    # Shared options live on each subcommand so they work after it: `travel-agent ask "..." -v`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", help="sonnet (default), opus, haiku, or a full model id")
    common.add_argument("--budget", type=float, help="max USD per request (default 0.50)")
    common.add_argument("-v", "--verbose", action="store_true", help="show every tool call")
    ap = argparse.ArgumentParser(prog="travel-agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", parents=[common], help="one question, then exit")
    a.add_argument("prompt")
    a.add_argument("--allow-pref-changes", action="store_true",
                   help="prompt to approve preference saves (denied by default in one-shot mode)")
    a.set_defaults(fn=_ask)
    c = sub.add_parser("chat", parents=[common], help="multi-turn conversation")
    c.set_defaults(fn=_chat)
    args = ap.parse_args(argv)
    try:
        return asyncio.run(args.fn(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
