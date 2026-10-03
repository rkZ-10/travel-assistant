"""Collect what happened in a run (tool calls, results, timing, cost) from SDK messages.
Saved as JSON per run, which is also what the evals will score."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage

from .config import bare_name


def _preview(content: Any, limit: int = 300) -> str:
    if isinstance(content, list):
        content = " ".join(
            c.get("text", "") if isinstance(c, dict) else str(c) for c in content
        )
    text = str(content or "")
    return text if len(text) <= limit else text[:limit] + "…"


@dataclass
class ToolCall:
    id: str
    tool: str
    input: dict[str, Any]
    is_error: bool | None = None
    result_preview: str = ""
    started: float = field(default_factory=time.monotonic, repr=False)
    duration_ms: int | None = None


class ToolTimer:
    """Times each tool call from PreToolUse to PostToolUse, keyed by tool_use_id.
    Message arrival times are batched by the SDK, so they can't be used for this."""

    def __init__(self) -> None:
        self._start: dict[str, float] = {}
        self.durations_ms: dict[str, int] = {}

    async def pre(self, _input: dict, tool_use_id: str | None, _ctx: Any) -> dict:
        if tool_use_id:
            self._start[tool_use_id] = time.monotonic()
        return {}

    async def post(self, _input: dict, tool_use_id: str | None, _ctx: Any) -> dict:
        if tool_use_id and tool_use_id in self._start:
            self.durations_ms[tool_use_id] = int((time.monotonic() - self._start.pop(tool_use_id)) * 1000)
        return {}


@dataclass
class RunTrace:
    prompt: str
    model: str
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    answer: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    denied: list[dict[str, Any]] = field(default_factory=list)
    turns: int | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    error: str | None = None

    def add(self, message: Any) -> None:
        if isinstance(message, AssistantMessage):
            texts = []
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    self.tool_calls.append(ToolCall(block.id, bare_name(block.name), dict(block.input)))
                elif isinstance(block, TextBlock):
                    texts.append(block.text)
            if texts:  # keep the latest assistant text as the answer
                self.answer = "\n".join(texts)
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            by_id = {c.id: c for c in self.tool_calls}
            for block in message.content:
                if isinstance(block, ToolResultBlock) and (call := by_id.get(block.tool_use_id)):
                    call.is_error = bool(block.is_error)
                    call.result_preview = _preview(block.content)
                    call.duration_ms = int((time.monotonic() - call.started) * 1000)
        elif isinstance(message, ResultMessage):
            self.turns = message.num_turns
            self.cost_usd = message.total_cost_usd
            self.duration_ms = message.duration_ms
            self.usage = message.usage or {}
            self.session_id = message.session_id
            if message.is_error:
                # The CLI can report failures (auth, API errors) with subtype "success" and the
                # message in `result`, so build the error from whichever field has the detail.
                detail = message.result or "; ".join(getattr(message, "errors", None) or []) or message.subtype
                reason = getattr(message, "terminal_reason", None) or message.subtype
                self.error = f"{reason}: {detail}"
                self.answer = ""  # don't present an error message as the assistant's answer
            elif message.result:
                self.answer = message.result

    def apply_timings(self, durations_ms: dict[str, int]) -> None:
        for call in self.tool_calls:
            if call.id in durations_ms:
                call.duration_ms = durations_ms[call.id]

    @property
    def tools_used(self) -> list[str]:
        return [c.tool for c in self.tool_calls]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for c in d["tool_calls"]:
            c.pop("started", None)
        return d

    def save(self, runs_dir: Path) -> Path:
        runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.started_at.replace(":", "").replace("-", "")
        path = runs_dir / f"{stamp}.json"
        n = 1
        while path.exists():
            path = runs_dir / f"{stamp}-{n}.json"
            n += 1
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path
