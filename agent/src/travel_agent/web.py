"""Local web backend for the chat UI: one agent session per WebSocket connection.

Protocol (JSON messages)
  client -> server   {"type": "message", "text": "..."}     ask something
                     {"type": "reset"}                        start a new conversation
  server -> client   {"type": "ready", "model": "..."}
                     {"type": "turn_start"}
                     {"type": "tool_start" | "tool_end" | "tool_blocked", ...}   live activity
                     {"type": "answer", "text", "turns", "cost_usd", "duration_ms", "tools"}
                     {"type": "error", "message"}

Binds to 127.0.0.1 only and rejects WebSocket connections from other origins, so a random website
can't drive the agent through your browser.
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, AgentConfig
from .guard import deny_all
from .runner import TravelAgent, is_transient_auth_error

UI_DIST = REPO_ROOT / "ui" / "dist"
DEV_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}  # Vite dev server

AgentFactory = Callable[[AgentConfig, Callable[[dict], Any]], Any]


def default_factory(cfg: AgentConfig, on_event: Callable[[dict], Any]) -> TravelAgent:
    # Preference writes need approval; the UI has no approval dialog yet, so they're denied and
    # the agent tells the user to use `travel-agent chat` (which asks y/N).
    return TravelAgent(cfg, approver=deny_all, on_event=on_event)


class Session:
    """Lazily starts the agent on the first message; one turn at a time."""

    def __init__(self, ws: WebSocket, cfg: AgentConfig, factory: AgentFactory) -> None:
        self.ws, self.cfg, self.factory = ws, cfg, factory
        self.agent: Any = None
        self.busy = False

    async def send(self, event: dict) -> None:
        with contextlib.suppress(Exception):  # client may have gone away mid-turn
            await self.ws.send_json(event)

    async def _ensure_agent(self) -> Any:
        if self.agent is None:
            self.agent = self.factory(self.cfg, self.send)
            await self.agent.__aenter__()
        return self.agent

    async def close(self) -> None:
        if self.agent is not None:
            with contextlib.suppress(Exception):
                await self.agent.__aexit__(None, None, None)
            self.agent = None

    async def handle(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "reset":
            await self.close()
            await self.send({"type": "ready", "model": self.cfg.model})
            return
        if kind != "message" or not str(msg.get("text", "")).strip():
            await self.send({"type": "error", "message": "Expected {type: 'message', text: '...'}"})
            return
        if self.busy:
            await self.send({"type": "error", "message": "Still working on the previous message."})
            return
        self.busy = True
        try:
            await self.send({"type": "turn_start"})
            agent = await self._ensure_agent()
            trace = await agent.ask(str(msg["text"]).strip())
            if trace.error:
                hint = (" Another Claude window was refreshing the shared login; try again in a minute."
                        if is_transient_auth_error(trace) else "")
                await self.send({"type": "error", "message": f"{trace.error}{hint}"})
                if is_transient_auth_error(trace):
                    await self.close()  # fresh session next time
            else:
                await self.send({
                    "type": "answer", "text": trace.answer, "turns": trace.turns,
                    "cost_usd": trace.cost_usd, "duration_ms": trace.duration_ms,
                    "tools": trace.tools_used,
                })
        except Exception as exc:  # noqa: BLE001 - surface to the UI instead of dropping the socket
            await self.send({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            await self.close()
        finally:
            self.busy = False


def create_app(cfg: AgentConfig | None = None, factory: AgentFactory = default_factory,
               port: int = 8765, ui_dist: Path = UI_DIST) -> FastAPI:
    cfg = cfg or AgentConfig.load()
    allowed_origins = DEV_ORIGINS | {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    app = FastAPI(title="Travel Assistant", docs_url=None, redoc_url=None)

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True, "model": cfg.model, "ui_built": ui_dist.exists()})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        origin = ws.headers.get("origin")
        if origin and origin not in allowed_origins:
            await ws.close(code=1008)  # policy violation
            return
        await ws.accept()
        session = Session(ws, cfg, factory)
        await session.send({"type": "ready", "model": cfg.model})
        try:
            while True:
                await session.handle(await ws.receive_json())
        except WebSocketDisconnect:
            pass
        finally:
            await session.close()

    if ui_dist.exists():
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")
    else:
        @app.get("/")
        async def no_ui() -> HTMLResponse:
            return HTMLResponse(
                "<h3>UI not built yet</h3><p>Run <code>npm install</code> and <code>npm run build</code> "
                "in the <code>ui/</code> folder, then restart <code>travel-agent web</code>.</p>"
            )

    return app


def serve(cfg: AgentConfig, port: int = 8765, open_browser: bool = False) -> None:
    import threading
    import webbrowser

    import uvicorn

    url = f"http://127.0.0.1:{port}"
    print(f"Travel assistant UI: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(cfg, port=port), host="127.0.0.1", port=port, log_level="warning")
