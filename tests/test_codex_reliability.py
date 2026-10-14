"""Regression cases from real Codex startup/visibility failures."""
import json
import os
import subprocess
import sys

from fastapi.testclient import TestClient

from vibegap.adapters.codex import install
from vibegap.adapters.codex.status import inspect_hooks
from vibegap.adapters import hook
from vibegap.config import Settings
from vibegap.daemon.app import create_app
from vibegap.daemon.codex_watcher import CodexWatcher
from vibegap.daemon.events import Agent, AgentEvent, EventKind, LifecycleKind
from vibegap.daemon.runtime import Runtime
from tests.test_runtime import FakeClock, FakeNotifier


def test_source_command_works_outside_repo_without_scripts_on_path(tmp_path):
    env = os.environ.copy()
    env['PATH'] = os.path.dirname(sys.executable)
    command = install.build_command('running') + ' --help'
    result = subprocess.run(command, shell=True, cwd=tmp_path, env=env,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_codex_hooks_async_except_session_end():
    document = install.apply_install({})
    for event, groups in document['hooks'].items():
        assert groups[0]['hooks'][0]['async'] == (event != 'SessionEnd')


def test_status_requires_valid_complete_configuration_and_real_hook(tmp_path):
    path = tmp_path / 'hooks.json'
    path.write_text('{invalid vibegap', encoding='utf-8')
    assert inspect_hooks(path)['status'] == 'error'
    path.write_text(json.dumps({'description': 'vibegap'}), encoding='utf-8')
    assert inspect_hooks(path)['status'] == 'available'
    document = install.apply_install({})
    path.write_text(json.dumps(document), encoding='utf-8')
    assert inspect_hooks(path)['status'] == 'configured'
    assert inspect_hooks(path, '2026-10-14T10:00:00')['status'] == 'connected'
    del document['hooks']['Stop']
    path.write_text(json.dumps(document), encoding='utf-8')
    assert inspect_hooks(path)['status'] == 'available'


def test_missing_executable_is_not_reported_connected(tmp_path):
    path = tmp_path / 'hooks.json'
    document = install.apply_install({}, helper_command='missing-vibegap-hook-987654.exe')
    path.write_text(json.dumps(document), encoding='utf-8')
    assert inspect_hooks(path, 'recent')['status'] == 'available'


def test_delayed_start_cannot_undo_stop_or_session_end():
    clock = FakeClock()
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=clock)
    client = TestClient(create_app(runtime))
    start = clock().isoformat()
    clock.advance(5)
    end = clock().isoformat()
    for event, ts in [('done', end), ('running', start)]:
        assert client.post('/hook/codex/' + event, params={'observed_at': ts},
                           json={'session_id': 's1'}).status_code == 200
    assert not runtime.snapshot().is_any_running
    assert runtime.recent_hook(Agent.CODEX) is not None
    client.post('/lifecycle/codex/detached', params={'observed_at': end}, json={'session_id': 's2'})
    client.post('/lifecycle/codex/attached', params={'observed_at': start}, json={'session_id': 's2'})
    client.post('/hook/codex/running', params={'observed_at': start}, json={'session_id': 's2'})
    assert runtime.snapshot().connected_count == 0
    assert not runtime.snapshot().is_any_running


def test_log_growth_keeps_long_task_alive_but_does_not_resurrect_stop(tmp_path):
    clock = FakeClock()
    runtime = Runtime(settings=Settings(auto_popup=False), notifier=FakeNotifier(), clock=clock)
    def emit(sid, kind, cwd):
        runtime.handle_event(AgentEvent(Agent.CODEX, sid, EventKind(kind), None))
    watcher = CodexWatcher(tmp_path, emit, clock,
                           touch=lambda sid: runtime.touch_running(Agent.CODEX, sid))
    watcher.poll()
    folder = tmp_path / clock().strftime('%Y/%m/%d')
    folder.mkdir(parents=True)
    path = folder / 'session.jsonl'
    path.write_text(json.dumps({'type': 'event_msg', 'payload': {'type': 'task_started'}}) + '\n', encoding='utf-8')
    watcher.poll()
    runtime.escape()
    for _ in range(3):
        clock.advance(20 * 60)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'token_count'}}) + '\n')
        watcher.poll()
        runtime.tick()
        assert runtime.snapshot().is_any_running
        assert not runtime.should_exit_idle()
    assert runtime.recent_hook(Agent.CODEX) is None  # watcher is not an HTTP hook
    runtime.handle_event(AgentEvent(Agent.CODEX, 'session', EventKind.DONE, None))
    with path.open('a', encoding='utf-8') as stream:
        stream.write('{}\n')
    watcher.poll()
    assert not runtime.snapshot().is_any_running
    clock.advance(31 * 60)
    runtime.tick()
    assert runtime.should_exit_idle()


def test_helper_records_replay_failure_without_payload(tmp_path, monkeypatch):
    from tests.test_hook_helper import _Stdin
    monkeypatch.setattr(hook, 'LOG_DIR', tmp_path)
    monkeypatch.setattr(sys, 'stdin', _Stdin(b'{"prompt":"PRIVATE PROMPT"}'))
    monkeypatch.setattr(sys, 'argv', ['vibegap-hook', '--agent', 'codex', '--event', 'running'])
    monkeypatch.setattr(hook, '_post_event', lambda *args: False)
    monkeypatch.setattr(hook, '_ensure_started', lambda port: True)
    hook.hook_main()
    text = next(tmp_path.glob('hook-*.log')).read_text(encoding='utf-8')
    assert 'stage=replay_failed' in text
    assert 'PRIVATE PROMPT' not in text


def test_activity_refresh_preserves_escape_and_event_order():
    clock = FakeClock()
    notifier = FakeNotifier()
    runtime = Runtime(settings=Settings(), notifier=notifier, clock=clock)
    runtime.handle_event(AgentEvent(Agent.CODEX, 's1', EventKind.RUNNING, clock()))
    clock.advance(20)
    runtime.tick()
    runtime.escape()
    clock.advance(20 * 60)
    done_at = clock()
    clock.advance(1)
    runtime.touch_running(Agent.CODEX, 's1')
    runtime.tick()
    assert runtime.snapshot().phase == 'HIDDEN'
    # Log activity must not move the lifecycle timestamp past a pending Stop.
    runtime.handle_event(AgentEvent(Agent.CODEX, 's1', EventKind.DONE, done_at))
    assert not runtime.snapshot().is_any_running
