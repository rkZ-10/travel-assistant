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
def client(tmp_path, error=None, bridge=None, key_only=False, login=True, cfg=None, seen=None):
    def factory(cfg, ev):
        if seen is not None:
            seen.append(cfg)
        return FakeAgent(cfg, ev, error)

    app = create_app(cfg or AgentConfig(model="haiku"), factory=factory,
                     ui_dist=tmp_path / "missing", bridge=bridge or FakeBridge(),
                     key_only=key_only, login_present=lambda: login)
    with TestClient(app) as c:
        yield c


def test_chat_turn_streams_activity_then_answer(tmp_path):
    with client(tmp_path) as c, c.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready" and ready["model"] == "haiku" and ready["auth"]["mode"] == "claude_login"
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
        assert c.get("/api/health").json() == {"ok": True, "model": "haiku", "ui_built": False, "key_only": False}
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


def test_expired_login_shows_sign_in_steps(tmp_path):
    err = "api_error: Failed to authenticate: OAuth session expired and could not be refreshed"
    with client(tmp_path, error=err) as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "hi"})
        msgs = [ws.receive_json() for _ in range(4)]
        assert msgs[-1]["type"] == "error" and "/login" in msgs[-1]["message"]


def test_login_expired_vs_transient():
    from travel_agent.runner import is_login_expired, is_transient_auth_error

    expired = RunTrace(prompt="p", model="m", error="api_error: Failed to authenticate: OAuth session expired and could not be refreshed")
    race = RunTrace(prompt="p", model="m", error="completed: Failed to refresh OAuth token: another Claude Code process is refreshing it")
    assert is_login_expired(expired) and not is_transient_auth_error(expired)
    assert is_transient_auth_error(race) and not is_login_expired(race)


KEY = "sk-ant-api03-" + "x" * 40


def test_no_login_asks_for_key_and_uses_it_only_for_this_session(tmp_path):
    seen = []
    with client(tmp_path, login=False, seen=seen) as c, c.websocket_connect("/ws") as ws:
        auth = ws.receive_json()["auth"]
        assert auth["mode"] == "none" and auth["needs_key"]
        ws.send_json({"type": "message", "text": "hi"})
        err = ws.receive_json()
        assert err["code"] == "needs_api_key" and not seen  # agent never started without credentials

        ws.send_json({"type": "set_api_key", "key": "not-a-key"})
        bad = ws.receive_json()
        assert bad["code"] == "bad_api_key" and "not-a-key" not in bad["message"]

        ws.send_json({"type": "set_api_key", "key": KEY})
        assert ws.receive_json()["auth"]["mode"] == "browser_key"
        ws.send_json({"type": "message", "text": "hi"})
        assert [ws.receive_json()["type"] for _ in range(4)][-1] == "answer"
        assert seen[0].env["ANTHROPIC_API_KEY"] == KEY

        ws.send_json({"type": "clear_api_key"})
        assert ws.receive_json()["auth"]["needs_key"]
    with client(tmp_path, login=False) as c, c.websocket_connect("/ws") as ws:  # a new session starts clean
        assert ws.receive_json()["auth"]["mode"] == "none"


def test_key_only_mode_ignores_local_login(tmp_path):
    with client(tmp_path, key_only=True, login=True) as c:
        assert c.get("/api/health").json()["key_only"] is True
        with c.websocket_connect("/ws") as ws:
            auth = ws.receive_json()["auth"]
            assert auth["mode"] == "none" and auth["reason"] == "key_only"


def test_server_env_key_reported(tmp_path):
    cfg = AgentConfig(model="haiku", env={"ANTHROPIC_API_KEY": KEY})
    with client(tmp_path, cfg=cfg, login=False) as c, c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["auth"]["mode"] == "server_key"


def test_rejected_key_is_dropped(tmp_path):
    with client(tmp_path, login=False, error="API Error: 401 authentication_error invalid x-api-key") as c, \
            c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_api_key", "key": KEY})
        ws.receive_json()
        ws.send_json({"type": "message", "text": "hi"})
        events = [ws.receive_json() for _ in range(5)]
        err = next(e for e in events if e["type"] == "error")
        assert err["code"] == "bad_api_key" and KEY not in err["message"]
        assert events[-1]["type"] == "ready" and events[-1]["auth"]["reason"] == "key_rejected"


def test_expired_login_offers_key(tmp_path):
    with client(tmp_path, error="OAuth session expired and could not be refreshed") as c, \
            c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "text": "hi"})
        events = [ws.receive_json() for _ in range(5)]
        assert events[-1]["type"] == "ready" and events[-1]["auth"]["reason"] == "login_expired"
        ws.send_json({"type": "reset"})  # signed in again -> retry with the login
        assert ws.receive_json()["auth"]["mode"] == "claude_login"
