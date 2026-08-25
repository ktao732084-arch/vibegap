"""跨层共享的事件与效果数据类型(纯数据,无 IO)。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Agent(str, Enum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    PI = "pi"
    WORKBUDDY = "workbuddy"
    DSH = "dsh"


class EventKind(str, Enum):
    RUNNING = "running"      # agent 开始执行一轮任务
    DONE = "done"            # 本轮任务结束
    ATTENTION = "attention"  # agent 停下来等用户(权限确认等)


@dataclass(frozen=True)
class AgentEvent:
    """Adapter 上报的原始事件。"""

    agent: Agent
    session_id: str
    kind: EventKind
    ts: datetime


@dataclass(frozen=True)
class AgentFinished:
    """会话层产出的效果:某 agent 本轮结束(DONE)或在等用户(ATTENTION)。"""

    agent: Agent
    kind: EventKind
