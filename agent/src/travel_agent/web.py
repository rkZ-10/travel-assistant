"""Local web backend for the chat UI: one agent session per WebSocket connection.

Protocol (JSON messages)
  client -> server   {"type": "message", "text": "..."}     ask something
                     {"type": "reset"}                        start a new conversation
  server -> client   {"type": "ready", "model": "..."}
                     {"type": "turn_start"}
                     {"type": "tool_start" | "tool_end" | "tool_blocked", ...}   live activity
                     {"type": "answer", "text", "turns", "cost_usd", "duration_ms", "tools"}
                     {"type": "error", "message"}

REST (user actions that don't need the model; they go to travel-mcp over a direct MCP client)
  GET  /api/preferences                 saved preferences
  PUT  /api/preferences  {changes}      edit them directly (the user is acting, so no approval step)
  POST /api/booking-options {booking_token, origin, destination, date, return_date}
                                         sellers + redirect links for a card (costs 1 SerpApi search)

Binds to 127.0.0.1 only and rejects requests and WebSocket connections from other origins, so a
random website can't drive the agent or change settings through your browser.
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, AgentConfig
from .guard import deny_all
from .mcp_bridge import BridgeError, McpBridge
from .runner import LOGIN_HINT, TravelAgent, is_login_expired, is_transient_auth_error

UI_DIST = REPO_ROOT / "ui" / "dist"
DEV_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}  # Vite dev server

AgentFactory = Callable[[AgentConfig, Callable[[dict], Any]], Any]


def default_factory(cfg: AgentConfig, on_event: Callable[[dict], Any]) -> TravelAgent:
    # Preference writes need approval; the UI has no approval dialog yet, so they're denied and
    # the agent tells the user to use `travel-agent chat` (which asks y/N).
    return TravelAgent(cfg, approver=deny_all, on_event=on_event, ui=True)


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
                if is_login_expired(trace):
                    message = LOGIN_HINT
                elif is_transient_auth_error(trace):
                    message = (f"{trace.error} Another Claude window was refreshing the shared login; "
                               "try again in a minute.")
                else:
                    message = trace.error
                await self.send({"type": "error", "message": message})
                if is_transient_auth_error(trace) or is_login_expired(trace):
                    await self.close()  # fresh session (and fresh credentials) next time
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
               port: int = 8765, ui_dist: Path = UI_DIST, bridge: Any = None) -> FastAPI:
    cfg = cfg or AgentConfig.load()
    allowed_origins = DEV_ORIGINS | {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    bridge = bridge if bridge is not None else McpBridge(cfg)
    state: dict[str, Any] = {"bridge_error": None}

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            await bridge.start()
        except Exception as exc:  # noqa: BLE001 - chat still works; panel/cards report it
            state["bridge_error"] = f"Couldn't start travel-mcp for the panel and booking links: {exc}"
        yield
        with contextlib.suppress(Exception):
            await bridge.stop()

    app = FastAPI(title="Travel Assistant", docs_url=None, redoc_url=None, lifespan=lifespan)

    def check_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins:
            raise HTTPException(403, "Cross-origin requests are not allowed")

    async def call(tool: str, args: dict) -> Any:
        if state["bridge_error"]:
            raise HTTPException(503, state["bridge_error"])
        try:
            return await bridge.call(tool, args)
        except BridgeError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/preferences")
    async def get_preferences(request: Request) -> JSONResponse:
        check_origin(request)
        return JSONResponse(await call("get_travel_preferences", {}))

    @app.put("/api/preferences")
    async def put_preferences(request: Request, body: dict = Body(...)) -> JSONResponse:
        check_origin(request)
        return JSONResponse(await call("update_travel_preferences", {"changes": body.get("changes") or {}}))

    @app.post("/api/booking-options")
    async def booking_options(request: Request, body: dict = Body(...)) -> JSONResponse:
        check_origin(request)
        keys = ("booking_token", "origin", "destination", "date", "return_date")
        args = {k: body.get(k) for k in keys if body.get(k)}
        if not all(k in args for k in keys[:4]):
            raise HTTPException(400, "booking_token, origin, destination and date are required")
        return JSONResponse(await call("get_booking_options", args))

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
