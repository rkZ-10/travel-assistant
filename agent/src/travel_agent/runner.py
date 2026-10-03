"""Build the agent and run it, one-shot (`ask`) or as a multi-turn chat session."""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

from .config import MCP_DIR, SERVER_NAME, TRAVEL_TOOLS, AgentConfig, mcp_command, mcp_name
from .guard import Approver, ToolGuard, deny_all
from .hooks import AgentHooks, EventSink
from .prompts import system_prompt
from .trace import RunTrace


def build_options(cfg: AgentConfig, hooks: AgentHooks | ToolGuard) -> ClaudeAgentOptions:
    if isinstance(hooks, ToolGuard):
        hooks = AgentHooks(hooks)
    cmd = mcp_command()
    return ClaudeAgentOptions(
        system_prompt=system_prompt(cfg.max_flight_searches),
        model=cfg.model,
        # No built-in tools (Bash, files, web): the agent can only use the travel server.
        tools=[],
        mcp_servers={
            SERVER_NAME: {
                "type": "stdio",
                "command": cmd[0],
                "args": cmd[1:],
                # Pass the full environment plus overrides, in case the CLI replaces rather than
                # merges (Python on Windows won't start without SYSTEMROOT etc.).
                **({"env": {**os.environ, **cfg.mcp_env}} if cfg.mcp_env else {}),
            }
        },
        strict_mcp_config=True,  # ignore any MCP servers from the user's Claude config
        setting_sources=[],  # ...and their CLAUDE.md / settings
        allowed_tools=[mcp_name(t) for t in TRAVEL_TOOLS],
        # Guardrails run before the permission check and can still deny allowed tools.
        hooks={
            # One combined hook: guard decides first; only allowed calls are timed and reported.
            "PreToolUse": [HookMatcher(matcher=None, hooks=[hooks.pre])],
            "PostToolUse": [HookMatcher(matcher=None, hooks=[hooks.post])],
            "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[hooks.post_failure])],
        },
        max_turns=cfg.max_turns,
        max_budget_usd=cfg.max_budget_usd,
        cwd=str(MCP_DIR),
        env=cfg.env,
    )


class TravelAgent:
    """One conversation. `ask()` can be called repeatedly; context carries over."""

    def __init__(self, cfg: AgentConfig, approver: Approver = deny_all, on_event: EventSink | None = None) -> None:
        self.cfg = cfg
        self.guard = ToolGuard(cfg.max_flight_searches, approver)
        self.hooks = AgentHooks(self.guard, emit=on_event)
        self.timer = self.hooks.timer
        self._client: ClaudeSDKClient | None = None

    async def __aenter__(self) -> "TravelAgent":
        self._client = ClaudeSDKClient(options=build_options(self.cfg, self.hooks))
        await self._client.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.disconnect()

    async def ask(self, prompt: str, save: bool = True) -> RunTrace:
        assert self._client, "use `async with TravelAgent(...)`"
        self.guard.reset()
        denied_before = len(self.guard.denied)
        trace = RunTrace(prompt=prompt, model=self.cfg.model)
        await self._client.query(prompt)
        async for message in self._client.receive_response():
            trace.add(message)
        trace.denied = self.guard.denied[denied_before:]
        trace.apply_timings(self.timer.durations_ms)
        if save:
            trace.save(self.cfg.runs_dir)
        return trace


@asynccontextmanager
async def open_agent(
    cfg: AgentConfig, approver: Approver = deny_all, on_event: EventSink | None = None
) -> AsyncIterator[TravelAgent]:
    async with TravelAgent(cfg, approver, on_event) as agent:
        yield agent


def is_transient_auth_error(trace: RunTrace) -> bool:
    """Shared Claude Code login: another Claude process refreshing the token at the same moment."""
    return bool(trace.error) and "refresh oauth token" in trace.error.lower()


async def ask_once(
    prompt: str,
    cfg: AgentConfig,
    approver: Approver = deny_all,
    retries: int = 2,
    retry_delay_s: float = 20.0,
    on_event: EventSink | None = None,
) -> RunTrace:
    for attempt in range(retries + 1):
        async with open_agent(cfg, approver, on_event) as agent:
            trace = await agent.ask(prompt, save=False)
        if not is_transient_auth_error(trace) or attempt == retries:
            break
        await asyncio.sleep(retry_delay_s)
    trace.save(cfg.runs_dir)
    return trace
