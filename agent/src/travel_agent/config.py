"""Agent configuration. The agent only talks to travel-mcp over MCP (stdio); it never
imports the server's code, so the boundary is the same one Claude Desktop uses."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_DIR = REPO_ROOT / "mcp-server"
SERVER_NAME = "travel"

# Every tool the server exposes. Anything else the model tries is denied.
TRAVEL_TOOLS = [
    "search_flights",
    "get_flight_status",
    "get_route_departures",
    "get_api_usage",
    "search_policies",
    "list_policy_sources",
    "get_travel_preferences",
    "update_travel_preferences",
]


def mcp_name(tool: str) -> str:
    return f"mcp__{SERVER_NAME}__{tool}"


def bare_name(full: str) -> str:
    prefix = f"mcp__{SERVER_NAME}__"
    return full[len(prefix):] if full.startswith(prefix) else full


def mcp_command(mcp_dir: Path = MCP_DIR, env: dict[str, str] | None = None) -> list[str]:
    """How to launch travel-mcp: TRAVEL_MCP_COMMAND (JSON list) > the server's own venv > uv."""
    env = os.environ if env is None else env
    if override := env.get("TRAVEL_MCP_COMMAND"):
        cmd = json.loads(override)
        if not (isinstance(cmd, list) and cmd and all(isinstance(c, str) for c in cmd)):
            raise ValueError("TRAVEL_MCP_COMMAND must be a JSON list of strings")
        return cmd
    win, posix = mcp_dir / ".venv" / "Scripts" / "python.exe", mcp_dir / ".venv" / "bin" / "python"
    for py in ((win, posix) if os.name == "nt" else (posix, win)):
        if py.exists() and (os.name == "nt") == (py == win):
            return [str(py), "-m", "travel_mcp.server"]
    return [sys.executable, "-m", "uv", "--directory", str(mcp_dir), "run", "travel-mcp"]


@dataclass
class AgentConfig:
    model: str = "sonnet"
    max_turns: int = 25
    max_budget_usd: float = 0.50  # hard stop per request
    max_flight_searches: int = 4  # per request; each live search costs 1 of ~250/month
    runs_dir: Path = field(default_factory=lambda: REPO_ROOT / ".data" / "agent_runs")
    env: dict[str, str] = field(default_factory=dict)
    mcp_env: dict[str, str] = field(default_factory=dict)  # extra env for the travel-mcp process
    ui: bool = False  # web-UI display tools (show_flight_cards); evals can turn it on per case

    @classmethod
    def load(cls, **overrides) -> "AgentConfig":
        dot = {k: v for k, v in dotenv_values(REPO_ROOT / ".env").items() if v}
        env = {}
        # API key from the environment wins; otherwise from the repo .env. If neither is set,
        # the bundled Claude Code CLI falls back to its own login.
        if key := (os.environ.get("ANTHROPIC_API_KEY") or dot.get("ANTHROPIC_API_KEY")):
            env["ANTHROPIC_API_KEY"] = key.strip()
        cfg = cls(env=env)
        model = os.environ.get("TRAVEL_AGENT_MODEL") or dot.get("TRAVEL_AGENT_MODEL")
        if model:
            cfg.model = model
        for k, v in overrides.items():
            if v is not None:
                setattr(cfg, k, v)
        return cfg
