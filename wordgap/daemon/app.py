"""FastAPI 路由:只做协议转换与校验,业务全部在 Runtime(§7.2)。"""
from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from wordgap.daemon.events import Agent, AgentEvent, EventKind
from wordgap.daemon.runtime import Runtime


class EventIn(BaseModel):
    """POST /event 请求体。非法枚举值由 pydantic 直接 422。"""

    model_config = ConfigDict(frozen=True)

    agent: Agent
    session_id: str
    event: EventKind
    ts: datetime | None = None


def create_app(runtime: Runtime) -> FastAPI:
    """应用工厂:注入 Runtime,便于测试。"""
    app = FastAPI(title="wordgap-daemon")

    @app.post("/event")
    def post_event(body: EventIn) -> dict:
        if not body.session_id.strip():
            raise HTTPException(status_code=422, detail="session_id must be non-empty")
        event = AgentEvent(
            agent=body.agent,
            session_id=body.session_id,
            kind=body.event,
            ts=body.ts or datetime.now(),
        )
        runtime.handle_event(event)
        return {"ok": True}

    @app.get("/state")
    def get_state() -> dict:
        snap = runtime.snapshot()
        return {
            "phase": snap.phase,
            "session_count": snap.session_count,
            "any_running": snap.is_any_running,
        }

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app
