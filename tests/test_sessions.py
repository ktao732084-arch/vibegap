"""会话状态机单测。"""
from datetime import datetime, timedelta

from vibegap.daemon.events import Agent, AgentEvent, AgentFinished, EventKind
from vibegap.daemon.sessions import (
    EMPTY_SESSIONS,
    any_running,
    cleanup_expired,
    reduce_event,
)

T0 = datetime(2026, 8, 25, 10, 0, 0)


def _event(kind: EventKind, agent: Agent = Agent.CLAUDE_CODE, sid: str = "s1", ts: datetime = T0):
    return AgentEvent(agent=agent, session_id=sid, kind=kind, ts=ts)


def test_running_sets_any_running():
    state, effects = reduce_event(EMPTY_SESSIONS, _event(EventKind.RUNNING))
    assert any_running(state)
    assert effects == []


def test_done_emits_finished_and_clears_running():
    state, _ = reduce_event(EMPTY_SESSIONS, _event(EventKind.RUNNING))
    state, effects = reduce_event(state, _event(EventKind.DONE, ts=T0 + timedelta(minutes=1)))
    assert not any_running(state)
    assert effects == [AgentFinished(agent=Agent.CLAUDE_CODE, kind=EventKind.DONE)]


def test_attention_emits_finished():
    state, _ = reduce_event(EMPTY_SESSIONS, _event(EventKind.RUNNING))
    _, effects = reduce_event(state, _event(EventKind.ATTENTION))
    assert effects == [AgentFinished(agent=Agent.CLAUDE_CODE, kind=EventKind.ATTENTION)]


def test_done_on_unknown_session_still_emits_finished():
    # daemon 中途重启丢失 RUNNING 记录时,done 依然要提醒用户
    _, effects = reduce_event(EMPTY_SESSIONS, _event(EventKind.DONE, agent=Agent.CODEX))
    assert effects == [AgentFinished(agent=Agent.CODEX, kind=EventKind.DONE)]


def test_multiple_sessions_any_running():
    state, _ = reduce_event(EMPTY_SESSIONS, _event(EventKind.RUNNING, sid="a"))
    state, _ = reduce_event(state, _event(EventKind.RUNNING, agent=Agent.CODEX, sid="b"))
    state, _ = reduce_event(state, _event(EventKind.DONE, sid="a"))
    assert any_running(state)  # codex 还在跑
    state, _ = reduce_event(state, _event(EventKind.DONE, agent=Agent.CODEX, sid="b"))
    assert not any_running(state)


def test_reduce_does_not_mutate_input_state():
    state1, _ = reduce_event(EMPTY_SESSIONS, _event(EventKind.RUNNING))
    before = dict(state1.sessions)
    reduce_event(state1, _event(EventKind.DONE))
    assert dict(state1.sessions) == before


def test_cleanup_expired_drops_orphans():
    state, _ = reduce_event(EMPTY_SESSIONS, _event(EventKind.RUNNING))
    ttl = timedelta(minutes=30)
    kept = cleanup_expired(state, T0 + timedelta(minutes=29), ttl)
    assert any_running(kept)
    cleaned = cleanup_expired(state, T0 + timedelta(minutes=31), ttl)
    assert not any_running(cleaned)
    assert len(cleaned.sessions) == 0


def test_cleanup_noop_returns_same_state_object():
    state, _ = reduce_event(EMPTY_SESSIONS, _event(EventKind.RUNNING))
    assert cleanup_expired(state, T0, timedelta(minutes=30)) is state
