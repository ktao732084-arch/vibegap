"""FastAPI 路由:只做协议转换与校验,业务全部在 Runtime(§7.2)。"""
from __future__ import annotations

import json
from datetime import datetime  # noqa: F401 - pydantic 模型注解运行时需要

from fastapi import FastAPI, HTTPException, Request
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
    def post_event(body: EventIn, request: Request) -> dict:
        _reject_browser(request)
        if not body.session_id.strip():
            raise HTTPException(status_code=422, detail="session_id must be non-empty")
        event = AgentEvent(
            agent=body.agent,
            session_id=body.session_id,
            kind=body.event,
            ts=body.ts,
        )
        runtime.handle_event(event)
        return {"ok": True}

    @app.post("/hook/{agent}/{event}")
    async def claude_hook(request: Request, agent: Agent, event: EventKind) -> dict:
        """接收 Claude-Code 兼容钩子的原始 stdin JSON(经 curl 透传),服务端提取 session_id。

        路径参数刻意不用查询串:URL 无 `&`,钩子命令不需要任何引号转义。
        钩子端因此只需一行 curl,免去 PowerShell 冷启动(实测 2.4s → ~50ms)。
        """
        _reject_browser(request)
        session_id = "unknown"
        try:
            payload = json.loads((await request.body()) or b"{}")
            if isinstance(payload, dict) and payload.get("session_id"):
                session_id = str(payload["session_id"])
        except json.JSONDecodeError:
            pass  # 钩子输入畸形不致命:退化为固定 session_id
        runtime.handle_event(
            AgentEvent(agent=agent, session_id=session_id, kind=event, ts=None)
        )
        return {"ok": True}

    @app.get("/state")
    def get_state() -> dict:
        snap = runtime.snapshot()
        return {
            "phase": snap.phase,
            "session_count": snap.session_count,
            "any_running": snap.is_any_running,
        }

    @app.post("/toggle")
    def toggle(request: Request) -> dict:
        """手动唤起/隐藏窗口(全局热键落地前的替代入口)。"""
        _reject_browser(request)
        runtime.hotkey_toggle()
        return {"ok": True, "phase": runtime.snapshot().phase}

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app


def _reject_browser(request: Request) -> None:
    """带 Origin/Referer 的请求来自浏览器页面(潜在 CSRF),adapter 脚本不会带。"""
    if request.headers.get("origin") or request.headers.get("referer"):
        raise HTTPException(status_code=403, detail="browser requests not allowed")
