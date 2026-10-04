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


class FakeBridge:
    def __init__(self, fail_start=False):
        self.calls, self.fail_start = [], fail_start
        self.prefs = {"home_airport": None}

    async def start(self):
        if self.fail_start:
            raise RuntimeError("no venv")

    async def stop(self):
        pass

    async def call(self, tool, args):
        from travel_agent.mcp_bridge import BridgeError

        self.calls.append((tool, args))
        if tool == "get_travel_preferences":
            return self.prefs
        if tool == "update_travel_preferences":
            if args["changes"].get("home_airport") == "Hyderabad":
                raise BridgeError("home_airport must be a 3-letter IATA code")
            self.prefs.update(args["changes"])
            return {"preferences": self.prefs, "changed": {"home_airport": [None, "HYD"]}, "message": "updated"}
        if tool == "get_booking_options":
            return {"options": [{"seller": "IndiGo", "is_airline": True, "booking_url": "https://www.google.com/travel/clk/f",
                                 "booking_post_data": "u=x"}], "links_valid_minutes": 10, "notes": []}


@contextmanager
def client(tmp_path, error=None, bridge=None):
    app = create_app(AgentConfig(model="haiku"), factory=lambda cfg, ev: FakeAgent(cfg, ev, error),
                     ui_dist=tmp_path / "missing", bridge=bridge or FakeBridge())
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


def test_preferences_endpoints(tmp_path):
    bridge = FakeBridge()
    with client(tmp_path, bridge=bridge) as c:
        assert c.get("/api/preferences").json() == {"home_airport": None}
        r = c.put("/api/preferences", json={"changes": {"home_airport": "HYD"}})
        assert r.status_code == 200 and r.json()["message"] == "updated"
        bad = c.put("/api/preferences", json={"changes": {"home_airport": "Hyderabad"}})
        assert bad.status_code == 400 and "IATA" in bad.json()["detail"]
        evil = c.put("/api/preferences", json={"changes": {}}, headers={"origin": "https://evil.example"})
        assert evil.status_code == 403
    assert ("update_travel_preferences", {"changes": {"home_airport": "HYD"}}) in bridge.calls


def test_booking_options_endpoint(tmp_path):
    bridge = FakeBridge()
    with client(tmp_path, bridge=bridge) as c:
        body = {"booking_token": "tok-123456789", "origin": "HYD", "destination": "MAA", "date": "2026-10-17"}
        r = c.post("/api/booking-options", json=body)
        assert r.status_code == 200 and r.json()["options"][0]["seller"] == "IndiGo"
        assert c.post("/api/booking-options", json={"origin": "HYD"}).status_code == 400
    assert bridge.calls[-1] == ("get_booking_options", body)


def test_bridge_start_failure_reported_but_chat_works(tmp_path):
    with client(tmp_path, bridge=FakeBridge(fail_start=True)) as c:
        r = c.get("/api/preferences")
        assert r.status_code == 503 and "travel-mcp" in r.json()["detail"]
        with c.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "ready"


def test_friendly_validation_errors():
    from travel_agent.mcp_bridge import friendly_error

    raw = ("1 validation error for update_travel_preferencesArguments\nchanges.home_airport\n"
           "  Value error, home_airport must be a 3-letter IATA code, got 'HYDERABAD' [type=value_error, input_value='x']")
    assert friendly_error(raw, "update_travel_preferences") == "home_airport must be a 3-letter IATA code, got 'HYDERABAD'"
    assert friendly_error("Error executing tool x: boom", "x") == "boom"
