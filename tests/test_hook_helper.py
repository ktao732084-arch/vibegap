"""瞬时 Hook helper:payload 只读一次,冷启动后原样重放。"""
from __future__ import annotations

import io
import sys

from vibegap.adapters import hook


class _Stdin:
    def __init__(self, payload: bytes):
        self.buffer = io.BytesIO(payload)


def test_hook_replays_exact_payload_after_lazy_start(monkeypatch):
    payload = b'{"session_id":"abc","cwd":"E:/repo"}'
    calls = []

    def post(agent, event, port, body, timeout):
        calls.append((agent, event, port, body, timeout))
        return len(calls) > 1

    monkeypatch.setattr(sys, "stdin", _Stdin(payload))
    monkeypatch.setattr(
        sys, "argv", ["vibegap-hook", "--agent", "claude-code", "--event", "running"]
    )
    monkeypatch.setattr(hook, "_post_event", post)
    monkeypatch.setattr(hook, "_ensure_started", lambda port: True)

    hook.hook_main()

    assert len(calls) == 2
    assert calls[0][3] == payload
    assert calls[1][3] == payload


def test_hook_does_not_start_when_fast_path_succeeds(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _Stdin(b"{}"))
    monkeypatch.setattr(
        sys, "argv", ["vibegap-hook", "--agent", "codex", "--event", "done"]
    )
    monkeypatch.setattr(hook, "_post_event", lambda *args: True)
    monkeypatch.setattr(
        hook,
        "_ensure_started",
        lambda port: (_ for _ in ()).throw(AssertionError("must not start")),
    )
    hook.hook_main()


def test_detach_never_resurrects_an_idle_core(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _Stdin(b'{"session_id":"s1"}'))
    monkeypatch.setattr(
        sys,
        "argv",
        ["vibegap-hook", "--agent", "claude-code", "--event", "detached"],
    )
    monkeypatch.setattr(hook, "_post_event", lambda *args: False)
    monkeypatch.setattr(
        hook,
        "_ensure_started",
        lambda port: (_ for _ in ()).throw(AssertionError("detach must not start core")),
    )
    hook.hook_main()


def test_health_requires_vibegap_identity(monkeypatch):
    monkeypatch.setattr(
        hook,
        "_request",
        lambda *args, **kwargs: (200, b'{"ok":true,"service":"other","protocol":1}'),
    )
    assert hook._health_matches(8765) is False
    monkeypatch.setattr(
        hook,
        "_request",
        lambda *args, **kwargs: (200, b'{"ok":true,"service":"vibegap","protocol":1}'),
    )
    assert hook._health_matches(8765) is True


def test_foreign_service_does_not_trigger_launch(monkeypatch):
    monkeypatch.setattr(hook, "_service_status", lambda port: hook._SERVICE_FOREIGN)
    monkeypatch.setattr(
        hook,
        "_launch_daemon",
        lambda port: (_ for _ in ()).throw(AssertionError("must not launch")),
    )
    assert hook._ensure_started(8765) is False


def test_startup_bind_window_is_not_mistaken_for_foreign_service(monkeypatch):
    statuses = iter(
        [hook._SERVICE_ABSENT, hook._SERVICE_FOREIGN, hook._SERVICE_MATCH]
    )
    monkeypatch.setattr(hook, "_service_status", lambda port: next(statuses))
    monkeypatch.setattr(hook, "_launch_daemon", lambda port: object())
    monkeypatch.setattr(hook.time, "sleep", lambda seconds: None)
    assert hook._ensure_started(8765) is True


def test_frozen_helper_relaunches_its_own_executable(monkeypatch):
    monkeypatch.setattr(hook.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        hook.sys, "executable", r"C:\Program Files\VibeGap\VibeGapHook.exe"
    )
    assert hook._daemon_command(9999) == [
        r"C:\Program Files\VibeGap\VibeGap.exe",
        "--daemon",
        "--port",
        "9999",
    ]
