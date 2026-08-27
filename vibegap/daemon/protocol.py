"""Daemon HTTP protocol models and hook-payload normalization."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from vibegap.config import RESULT_FAIL, RESULT_PASS, RESULT_SKIP
from vibegap.daemon.events import Agent, EventKind


class EventIn(BaseModel):
    """POST /event request body."""

    model_config = ConfigDict(frozen=True)

    agent: Agent
    session_id: str
    event: EventKind
    ts: datetime | None = None


class PanelCommitIn(BaseModel):
    """POST /panel/commit request body."""

    model_config = ConfigDict(frozen=True)

    result: Literal[RESULT_PASS, RESULT_FAIL, RESULT_SKIP]
    typo_count: int = Field(default=0, ge=0)


class PanelApi(Protocol):
    """Smallest progress interface required by panel routes."""

    def next_word(self) -> dict: ...

    def commit_word(self, result: str, typo_count: int = 0) -> dict: ...

    def get_progress(self) -> dict: ...


def parse_hook_payload(raw: bytes) -> tuple[str, str]:
    """Return (session_id, cwd), tolerating malformed hook input."""
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return "unknown", ""
    if not isinstance(payload, dict):
        return "unknown", ""
    event_name = str(payload.get("hook_event_name", ""))
    if event_name in ("SubagentStart", "SubagentStop") and payload.get("agent_id"):
        session_id = str(payload["agent_id"])
    else:
        session_id = str(payload.get("session_id") or "unknown")
    return session_id, str(payload.get("cwd") or "")
