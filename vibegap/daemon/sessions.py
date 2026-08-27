"""会话状态机:跟踪每个 (agent, session) 是否在运行。纯函数,无 IO(§7.3)。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping

from vibegap.daemon.events import AgentEvent, AgentFinished, Agent, EventKind


@dataclass(frozen=True)
class SessionKey:
    agent: Agent
    session_id: str


@dataclass(frozen=True)
class SessionInfo:
    is_running: bool
    last_event_at: datetime
    cwd: str = ""


@dataclass(frozen=True)
class SessionsState:
    sessions: Mapping[SessionKey, SessionInfo]


EMPTY_SESSIONS = SessionsState(sessions=MappingProxyType({}))


def any_running(state: SessionsState) -> bool:
    """是否存在至少一个正在运行的会话。"""
    return any(info.is_running for info in state.sessions.values())


def reduce_event(
    state: SessionsState, event: AgentEvent
) -> tuple[SessionsState, list[AgentFinished]]:
    """处理一条 adapter 事件,返回新状态与效果列表。

    DONE/ATTENTION 即使来自未知会话也上报 AgentFinished
    (daemon 中途重启会丢失 RUNNING 记录,但用户仍需要提醒)。
    """
    key = SessionKey(event.agent, event.session_id)
    existing = state.sessions.get(key)
    cwd = event.cwd or (existing.cwd if existing else "")
    info = SessionInfo(
        is_running=(event.kind is EventKind.RUNNING), last_event_at=event.ts, cwd=cwd
    )
    new_state = _with_session(state, key, info)
    if event.kind is EventKind.RUNNING:
        return new_state, []
    if existing is not None and not existing.is_running:
        return new_state, []  # Hook + 日志 watcher 可能重复上报同一次结束
    return new_state, [AgentFinished(agent=event.agent, kind=event.kind)]


def cleanup_expired(state: SessionsState, now: datetime, ttl: timedelta) -> SessionsState:
    """清理超过 ttl 未活动的会话(agent 崩溃/被杀的兜底),静默不产生效果。"""
    alive = {
        key: info
        for key, info in state.sessions.items()
        if now - info.last_event_at <= ttl
    }
    if len(alive) == len(state.sessions):
        return state
    return SessionsState(sessions=MappingProxyType(alive))


def remove_session(state: SessionsState, key: SessionKey) -> SessionsState:
    """宿主退出时静默移除会话,避免把进程退出误报为一次任务完成。"""
    if key not in state.sessions:
        return state
    remaining = dict(state.sessions)
    del remaining[key]
    return SessionsState(sessions=MappingProxyType(remaining))


def _with_session(
    state: SessionsState, key: SessionKey, info: SessionInfo
) -> SessionsState:
    merged = dict(state.sessions)
    merged[key] = info
    return SessionsState(sessions=MappingProxyType(merged))
