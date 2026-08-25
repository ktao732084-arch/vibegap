"""FastAPI 路由测试(TestClient)。"""
import pytest
from fastapi.testclient import TestClient

from wordgap.config import Settings
from wordgap.daemon.app import create_app
from wordgap.daemon.runtime import Runtime
from tests.test_runtime import FakeClock, FakeNotifier


@pytest.fixture
def client():
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=FakeClock())
    return TestClient(create_app(runtime))


def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_post_event_and_state(client):
    resp = client.post(
        "/event", json={"agent": "claude-code", "session_id": "s1", "event": "running"}
    )
    assert resp.status_code == 200
    state = client.get("/state").json()
    assert state["any_running"] is True
    assert state["phase"] == "ARMED"
    assert state["session_count"] == 1


def test_post_event_done_flow(client):
    client.post("/event", json={"agent": "codex", "session_id": "x", "event": "running"})
    client.post("/event", json={"agent": "codex", "session_id": "x", "event": "done"})
    state = client.get("/state").json()
    assert state["any_running"] is False
    assert state["phase"] == "HIDDEN"


def test_invalid_agent_rejected(client):
    resp = client.post(
        "/event", json={"agent": "skynet", "session_id": "s1", "event": "running"}
    )
    assert resp.status_code == 422


def test_invalid_event_kind_rejected(client):
    resp = client.post(
        "/event", json={"agent": "codex", "session_id": "s1", "event": "exploded"}
    )
    assert resp.status_code == 422


def test_empty_session_id_rejected(client):
    resp = client.post(
        "/event", json={"agent": "codex", "session_id": "  ", "event": "running"}
    )
    assert resp.status_code == 422


def test_browser_origin_rejected(client):
    resp = client.post(
        "/event",
        json={"agent": "codex", "session_id": "s1", "event": "running"},
        headers={"Origin": "http://evil.example"},
    )
    assert resp.status_code == 403


def test_hook_endpoint_extracts_session_id(client):
    resp = client.post(
        "/hook/claude-code/running",
        content=b'{"session_id": "abc-123", "cwd": "E:/x"}',
    )
    assert resp.status_code == 200
    assert client.get("/state").json()["phase"] == "ARMED"


def test_hook_endpoint_tolerates_garbage_body(client):
    assert client.post("/hook/codex/done", content=b"{not json").status_code == 200
    assert client.post("/hook/codex/done", content=b"").status_code == 200


def test_hook_endpoint_rejects_unknown_agent_or_event(client):
    assert client.post("/hook/skynet/running", content=b"{}").status_code == 422
    assert client.post("/hook/codex/exploded", content=b"{}").status_code == 422


def test_hook_endpoint_rejects_browser_origin(client):
    resp = client.post(
        "/hook/codex/done", content=b"{}", headers={"Origin": "http://evil.example"}
    )
    assert resp.status_code == 403


def test_dsh_agent_accepted(client):
    resp = client.post(
        "/event", json={"agent": "dsh", "session_id": "s1", "event": "running"}
    )
    assert resp.status_code == 200
