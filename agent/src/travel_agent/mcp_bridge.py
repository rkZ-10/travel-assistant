"""A direct MCP client to travel-mcp for user actions in the UI that don't need the model:
reading and editing preferences, and fetching booking options when a card is clicked.

Still goes over MCP (same boundary as the agent), so the web layer never imports server code.
"""
from __future__ import annotations

import contextlib
import os
from typing import Any

from mcp import Client, StdioServerParameters

from .config import AgentConfig, mcp_command


class BridgeError(RuntimeError):
    """A tool returned an error (e.g. validation); the message is safe to show the user."""


def friendly_error(text: str, tool: str) -> str:
    """'1 validation error ... Value error, home_airport must be ...' -> 'home_airport must be ...'"""
    import re

    values = re.findall(r"Value error, ([^\n]+?)(?: \[type=|$)", text, re.M)
    if values:
        return "; ".join(v.strip() for v in values)
    return text.replace(f"Error executing tool {tool}: ", "").strip()


class McpBridge:
    def __init__(self, cfg: AgentConfig) -> None:
        self.cfg = cfg
        self._stack: contextlib.AsyncExitStack | None = None
        self._client: Any = None

    async def start(self) -> None:
        cmd = mcp_command()
        params = StdioServerParameters(command=cmd[0], args=cmd[1:], env={**os.environ, **self.cfg.mcp_env})
        self._stack = contextlib.AsyncExitStack()
        self._client = await self._stack.enter_async_context(Client(params))

    async def stop(self) -> None:
        if self._stack:
            await self._stack.aclose()
        self._stack = self._client = None

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        if self._client is None:
            raise BridgeError("travel-mcp isn't running")
        result = await self._client.call_tool(tool, args)
        if result.is_error:
            text = " ".join(getattr(c, "text", "") for c in result.content) or "tool failed"
            raise BridgeError(friendly_error(text, tool))
        return result.structured_content
