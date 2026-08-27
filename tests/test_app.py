"""FastAPI 路由测试(TestClient)。"""
import pytest
from fastapi.testclient import TestClient

from vibegap.config import Settings
from vibegap.daemon.app import create_app
from vibegap.daemon.runtime import Runtime
from tests.test_runtime import FakeClock, FakeNotifier


class FakePanel:
    def __init__(self):
        self.commits = []

    def next_word(self):
        return {
            "name": "shared",
            "trans": ["共享的"],
            "usphone": "ʃerd",
            "position": 3,
            "total": 10,
        }

    def commit_word(self, result, typo_count=0):
        self.commits.append((result, typo_count))
        return {"cursor": 4, "total": 10, "round_completed": False}

    def get_progress(self):
        return {
            "cursor": 3,
            "total": 10,
            "mode": "shuffled",
            "book_name": "test",
            "today": 2,
            "goal": 50,
        }


@pytest.fixture
def panel():
    return FakePanel()


@pytest.fixture
def client(panel):
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=FakeClock())
    return TestClient(create_app(runtime, panel))


def test_healthz(client):
    assert client.get("/healthz").json() == {
        "ok": True,
        "service": "vibegap",
        "protocol": 1,
    }


def test_lifecycle_attach_and_detach(client):
    payload = {"session_id": "host-1", "hook_event_name": "SessionStart"}
    response = client.post("/lifecycle/claude-code/attached", json=payload)
    assert response.status_code == 200
    assert client.get("/state").json()["connected_count"] == 1

    client.post(
        "/hook/claude-code/running",
        json={"session_id": "host-1", "hook_event_name": "UserPromptSubmit"},
    )
    assert client.get("/state").json()["any_running"] is True

    response = client.post(
        "/lifecycle/claude-code/detached",
        json={"session_id": "host-1", "hook_event_name": "SessionEnd"},
    )
    assert response.status_code == 200
    state = client.get("/state").json()
    assert state["connected_count"] == 0
    assert state["any_running"] is False


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


def test_post_event_with_offset_timestamp_survives_tick():
    clock = FakeClock()
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=clock)
    local_client = TestClient(create_app(runtime))
    response = local_client.post(
        "/event",
        json={
            "agent": "codex",
            "session_id": "aware-ts",
            "event": "running",
            "ts": "2026-08-25T10:00:00+08:00",
        },
    )
    assert response.status_code == 200
    clock.advance(1)
    runtime.tick()
    assert runtime.snapshot().phase in ("HIDDEN", "ARMED")


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


def test_codex_subagent_hooks_use_distinct_agent_ids(client):
    for agent_id in ("agent-a", "agent-b"):
        response = client.post(
            "/hook/codex/running",
            json={
                "hook_event_name": "SubagentStart",
                "session_id": "parent-session",
                "agent_id": agent_id,
            },
        )
        assert response.status_code == 200
    state = client.get("/state").json()
    assert state["session_count"] == 2
    client.post(
        "/hook/codex/done",
        json={
            "hook_event_name": "SubagentStop",
            "session_id": "parent-session",
            "agent_id": "agent-a",
        },
    )
    assert client.get("/state").json()["any_running"] is True


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


def test_toggle_endpoint(client):
    resp = client.post("/toggle")
    assert resp.status_code == 200
    assert resp.json()["phase"] == "SHOWING"
    resp = client.post("/toggle")
    assert resp.json()["phase"] == "HIDDEN"


def test_toggle_rejects_browser_origin(client):
    resp = client.post("/toggle", headers={"Origin": "http://evil.example"})
    assert resp.status_code == 403


def test_panel_state_reports_shared_progress(client):
    response = client.get(
        "/panel/state", headers={"Origin": "http://127.0.0.1:3080"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3080"
    assert response.json() == {
        "ok": True,
        "ready": True,
        "progress": {
            "cursor": 3,
            "total": 10,
            "mode": "shuffled",
            "book_name": "test",
            "today": 2,
            "goal": 50,
        },
    }


def test_panel_word_progress_and_commit(client, panel):
    origin = {"Origin": "http://localhost:3080"}
    assert client.get("/panel/next-word", headers=origin).json()["name"] == "shared"
    assert client.get("/panel/progress", headers=origin).json()["cursor"] == 3
    response = client.post(
        "/panel/commit", headers=origin, json={"result": "fail", "typo_count": 2}
    )
    assert response.json()["cursor"] == 4
    assert panel.commits == [("fail", 2)]


def test_panel_commit_rejects_negative_typos(client):
    response = client.post(
        "/panel/commit", json={"result": "pass", "typo_count": -1}
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "http://localhost.evil.example:3080",
        "file://localhost",
        "https://127.0.0.2:3080",
    ],
)
def test_panel_rejects_untrusted_browser_origins(client, origin):
    assert client.get("/panel/state", headers={"Origin": origin}).status_code == 403


def test_panel_cors_preflight_is_scoped(client):
    headers = {
        "Origin": "https://localhost:4443",
        "Access-Control-Request-Method": "POST",
    }
    response = client.options("/panel/commit", headers=headers)
    assert response.status_code == 204
    assert response.headers["access-control-allow-methods"] == "GET, POST, OPTIONS"
    assert client.options("/event", headers=headers).status_code == 405


def test_existing_browser_rejection_survives_panel_cors(client):
    response = client.post(
        "/event",
        json={"agent": "codex", "session_id": "s1", "event": "running"},
        headers={"Origin": "http://localhost:3080"},
    )
    assert response.status_code == 403


def test_panel_without_service_is_unavailable():
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=FakeClock())
    client = TestClient(create_app(runtime))
    assert client.get("/panel/state").status_code == 503


def test_panel_state_not_ready_when_wordbook_missing():
    panel = FakePanel()
    panel.get_progress = lambda: {"error": "no_wordbook"}
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=FakeClock())
    client = TestClient(create_app(runtime, panel))
    assert client.get("/panel/state").json() == {
        "ok": True,
        "ready": False,
        "progress": {"error": "no_wordbook"},
    }
