from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from travel_agent.config import AgentConfig
from travel_agent.trace import RunTrace
from travel_agent.web import create_app


class FakeAgent:
    instances = 0

    def __init__(self, cfg, on_event, error=None):
        self.on_event, self.error = on_event, error
        self.prompts = []
        FakeAgent.instances += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def ask(self, prompt):
        self.prompts.append(prompt)
        await self.on_event({"type": "tool_start", "id": "t1", "tool": "search_flights", "label": "Searching flights"})
        await self.on_event({"type": "tool_end", "id": "t1", "tool": "search_flights", "ok": True, "duration_ms": 12})
        t = RunTrace(prompt=prompt, model="m", answer=f"echo: {prompt}", turns=2, cost_usd=0.01, error=self.error)
        return t


@contextmanager
def client(tmp_path, error=None):
    app = create_app(AgentConfig(model="haiku"), factory=lambda cfg, ev: FakeAgent(cfg, ev, error),
                     ui_dist=tmp_path / "missing")
    with TestClient(app) as c:
        yield c


def test_chat_turn_streams_activity_then_answer(tmp_path):
    with client(tmp_path) as c, c.websocket_connect("/ws") as ws:
        assert ws.receive_json() == {"type": "ready", "model": "haiku"}
        ws.send_json({"type": "message", "text": "HYD to MAA"})
        kinds = [ws.receive_json() for _ in range(4)]
        assert [k["type"] for k in kinds] == ["turn_start", "tool_start", "tool_end", "answer"]
        assert kinds[-1]["text"] == "echo: HYD to MAA" and kinds[-1]["turns"] == 2


def test_session_reused_across_turns_and_reset(tmp_path):
    FakeAgent.instances = 0
    with client(tmp_path) as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        for text in ["one", "two"]:
            ws.send_json({"type": "message", "text": text})
            while ws.receive_json()["type"] != "answer":
                pass
        assert FakeAgent.instances == 1
        ws.send_json({"type": "reset"})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "message", "text": "three"})
        while ws.receive_json()["type"] != "answer":
            pass
        assert FakeAgent.instances == 2


def test_errors_are_reported(tmp_path):
    with client(tmp_path, error="completed: Failed to refresh OAuth token: x") as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "hi"})
        msgs = [ws.receive_json() for _ in range(4)]
        assert msgs[-1]["type"] == "error" and "refreshing the shared login" in msgs[-1]["message"]
        ws.send_json({"type": "bogus"})
        assert ws.receive_json()["type"] == "error"


def test_foreign_origin_rejected(tmp_path):
    with client(tmp_path) as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as ws:
                ws.receive_json()


def test_health_and_unbuilt_ui(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/api/health").json() == {"ok": True, "model": "haiku", "ui_built": False}
        assert "npm run build" in c.get("/").text
