"""SDK hook callbacks: guardrail, timing and live activity events in one place.

One combined PreToolUse hook (instead of separate guard and timer hooks) so a denied call is
reported as "blocked" and never as "started", whatever order the SDK runs hooks in.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from .activity import label
from .config import bare_name
from .guard import ToolGuard
from .trace import ToolTimer
from .ui_tools import SearchRegistry

Event = dict[str, Any]
EventSink = Callable[[Event], Any]  # sync or async


class AgentHooks:
    def __init__(self, guard: ToolGuard, timer: ToolTimer | None = None, emit: EventSink | None = None) -> None:
        self.guard = guard
        self.timer = timer or ToolTimer()
        self.emit = emit
        self.registry = SearchRegistry()
        self._tools: dict[str, str] = {}

    async def _send(self, event: Event) -> None:
        if self.emit is None:
            return
        result = self.emit(event)
        if inspect.isawaitable(result):
            await result

    async def pre(self, hook_input: dict, tool_use_id: str | None, ctx: Any) -> dict:
        out = await self.guard.hook(hook_input, tool_use_id, ctx)
        tool = bare_name(hook_input.get("tool_name", "")).replace("mcp__ui__", "")
        args = hook_input.get("tool_input") or {}
        if out:  # denied
            reason = out["hookSpecificOutput"]["permissionDecisionReason"]
            await self._send({"type": "tool_blocked", "id": tool_use_id, "tool": tool,
                              "label": label(tool, args), "reason": reason})
            return out
        await self.timer.pre(hook_input, tool_use_id, ctx)
        if tool_use_id:
            self._tools[tool_use_id] = tool
        await self._send({"type": "tool_start", "id": tool_use_id, "tool": tool,
                          "label": label(tool, args), "input": args})
        return {}

    async def _end(self, tool_use_id: str | None, ok: bool, ctx: Any, error: str | None = None) -> dict:
        await self.timer.post({}, tool_use_id, ctx)
        await self._send({"type": "tool_end", "id": tool_use_id, "tool": self._tools.pop(tool_use_id or "", ""),
                          "ok": ok, "duration_ms": self.timer.durations_ms.get(tool_use_id or ""), "error": error})
        return {}

    async def post(self, hook_input: dict, tool_use_id: str | None, ctx: Any) -> dict:
        if bare_name(hook_input.get("tool_name", "")) == "search_flights":
            self.registry.record(hook_input.get("tool_input") or {}, hook_input.get("tool_response"))
        return await self._end(tool_use_id, True, ctx)

    async def post_failure(self, hook_input: dict, tool_use_id: str | None, ctx: Any) -> dict:
        return await self._end(tool_use_id, False, ctx, str(hook_input.get("error") or "tool failed"))
