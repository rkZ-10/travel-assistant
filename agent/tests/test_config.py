import json
import os

import pytest

from travel_agent.config import AgentConfig, bare_name, mcp_command, mcp_name
from travel_agent.guard import ToolGuard
from travel_agent.prompts import IST, system_prompt
from travel_agent.runner import build_options


def test_names_roundtrip():
    assert bare_name(mcp_name("search_flights")) == "search_flights"
    assert bare_name("Bash") == "Bash"


def test_mcp_command_override_and_fallback(tmp_path):
    env = {"TRAVEL_MCP_COMMAND": json.dumps(["python", "-m", "travel_mcp.server"])}
    assert mcp_command(tmp_path, env) == ["python", "-m", "travel_mcp.server"]
    with pytest.raises(ValueError):
        mcp_command(tmp_path, {"TRAVEL_MCP_COMMAND": '"python"'})
    assert mcp_command(tmp_path, {})[-2:] == ["run", "travel-mcp"]  # no venv yet -> uv


def test_mcp_command_prefers_server_venv(tmp_path):
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    py = tmp_path / ".venv" / sub[0] / sub[1]
    py.parent.mkdir(parents=True)
    py.write_text("")
    assert mcp_command(tmp_path, {}) == [str(py), "-m", "travel_mcp.server"]


def test_system_prompt_has_date_and_budget():
    from datetime import datetime

    p = " ".join(system_prompt(4, datetime(2026, 10, 2, 9, 0, tzinfo=IST)).split())
    assert "2026-10-02 (Friday)" in p and "at most 4 searches" in p


def test_options_lock_agent_to_travel_tools(monkeypatch):
    monkeypatch.setenv("TRAVEL_MCP_COMMAND", json.dumps(["py", "-m", "travel_mcp.server"]))
    cfg = AgentConfig(model="haiku", max_budget_usd=0.2)
    o = build_options(cfg, ToolGuard())
    assert o.tools == [] and o.strict_mcp_config and o.setting_sources == []
    assert o.mcp_servers["travel"] == {"type": "stdio", "command": "py", "args": ["-m", "travel_mcp.server"]}
    assert all(t.startswith("mcp__travel__") for t in o.allowed_tools) and len(o.allowed_tools) == 8
    assert o.model == "haiku" and o.max_budget_usd == 0.2
    assert "PreToolUse" in o.hooks and "PostToolUse" not in o.hooks
    from travel_agent.trace import ToolTimer

    timed = build_options(cfg, ToolGuard(), ToolTimer())
    pre = timed.hooks["PreToolUse"][0].hooks
    assert pre[0].__func__.__name__ == "hook" and len(pre) == 2  # guard runs before the timer
    assert "PostToolUse" in timed.hooks


async def test_ask_once_retries_transient_auth_error(monkeypatch, tmp_path):
    from travel_agent import runner
    from travel_agent.trace import RunTrace

    calls = []

    class FakeAgent:
        async def ask(self, prompt, save=True):
            calls.append(prompt)
            t = RunTrace(prompt=prompt, model="m")
            if len(calls) == 1:
                t.error = "completed: Failed to refresh OAuth token: another Claude Code process is refreshing it"
            else:
                t.answer = "ok"
            return t

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_open(cfg, approver):
        yield FakeAgent()

    monkeypatch.setattr(runner, "open_agent", fake_open)
    t = await runner.ask_once("q", AgentConfig(runs_dir=tmp_path), retry_delay_s=0)
    assert t.answer == "ok" and len(calls) == 2
    assert len(list(tmp_path.glob("*.json"))) == 1  # only the final attempt is saved
