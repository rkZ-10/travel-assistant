"""travel-agent: `ask` for one question, `chat` for a conversation."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from .config import AgentConfig
from .guard import deny_all
from .runner import LOGIN_HINT, ask_once, is_login_expired, open_agent
from .trace import RunTrace


async def console_approver(tool: str, tool_input: dict[str, Any]) -> bool:
    changes = tool_input.get("changes", tool_input)
    print(f"\n[approval] The assistant wants to save preferences:\n{json.dumps(changes, indent=2)}")
    answer = await asyncio.to_thread(input, "Save these? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def live_printer(event: dict) -> None:
    """-v: show tool activity as it happens."""
    if event["type"] == "tool_start":
        print(f"  · {event['label']}…", flush=True)
    elif event["type"] == "tool_blocked":
        print(f"  ✗ blocked: {event['label']} ({event['reason']})", flush=True)
    elif event["type"] == "tool_end" and not event.get("ok"):
        print(f"  ! {event.get('tool')} failed: {event.get('error')}", flush=True)


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
    trace = await ask_once(args.prompt, cfg, approver, on_event=live_printer if args.verbose else None)
    if trace.answer:
        print(trace.answer)
    print(_summary(trace, args.verbose))
    if is_login_expired(trace):
        print("  " + LOGIN_HINT)
    elif trace.error and "oauth" in trace.error.lower():
        print("  hint: another Claude Code/Desktop process kept refreshing the shared login (retried "
              "automatically). Try again in a minute, or close other Claude Code windows.")
    return 1 if trace.error else 0


async def _chat(args: argparse.Namespace) -> int:
    cfg = AgentConfig.load(model=args.model, max_budget_usd=args.budget)
    print("Travel assistant. Ask about flights, fares, baggage or status. Ctrl+C or 'exit' to quit.")
    async with open_agent(cfg, console_approver, live_printer if args.verbose else None) as agent:
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
    w = sub.add_parser("web", parents=[common], help="chat in the browser (React UI)")
    w.add_argument("--port", type=int, default=8765)
    w.add_argument("--open", action="store_true", help="open the browser")
    w.set_defaults(fn=None, web=True)
    args = ap.parse_args(argv)
    if getattr(args, "web", False):
        from .web import serve

        serve(AgentConfig.load(model=args.model, max_budget_usd=args.budget), args.port, args.open)
        return 0
    try:
        return asyncio.run(args.fn(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
