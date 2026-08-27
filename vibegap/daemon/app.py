"""FastAPI 路由:只做协议转换与校验,业务全部在 Runtime(§7.2)。"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime  # noqa: F401 - pydantic 模型注解运行时需要
from typing import Literal, Protocol

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse, Response

from vibegap.config import (
    PANEL_ORIGIN_PATTERN,
    RESULT_FAIL,
    RESULT_PASS,
    RESULT_SKIP,
)

logger = logging.getLogger(__name__)
from vibegap.daemon.events import Agent, AgentEvent, EventKind
from vibegap.daemon.runtime import Runtime


class EventIn(BaseModel):
    """POST /event 请求体。非法枚举值由 pydantic 直接 422。"""

    model_config = ConfigDict(frozen=True)

    agent: Agent
    session_id: str
    event: EventKind
    ts: datetime | None = None


class PanelCommitIn(BaseModel):
    """POST /panel/commit 请求体。"""

    model_config = ConfigDict(frozen=True)

    result: Literal[RESULT_PASS, RESULT_FAIL, RESULT_SKIP]  # 与 config.VALID_RESULTS 同源
    typo_count: int = Field(default=0, ge=0)


class PanelApi(Protocol):
    """daemon 面板路由所需的最小进度接口。"""

    def next_word(self) -> dict:
        """读取共享游标指向的单词。"""
        ...

    def commit_word(self, result: str, typo_count: int = 0) -> dict:
        """提交结果并推进共享游标。"""
        ...

    def get_progress(self) -> dict:
        """读取共享进度。"""
        ...


def create_app(runtime: Runtime, panel: PanelApi | None = None) -> FastAPI:
    """应用工厂:注入 Runtime,便于测试。"""
    app = FastAPI(title="vibegap-daemon")
    app.middleware("http")(_panel_cors)
    _mount_event_routes(app, runtime)
    _mount_control_routes(app, runtime)
    _mount_panel_routes(app, panel)
    return app


def _mount_event_routes(app: FastAPI, runtime: Runtime) -> None:
    """挂载 adapter 事件入口。"""

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
        cwd = ""
        try:
            payload = json.loads((await request.body()) or b"{}")
            if isinstance(payload, dict):
                session_id = _hook_session_id(payload)
                if payload.get("cwd"):
                    cwd = str(payload["cwd"])
        except json.JSONDecodeError:
            pass  # 钩子输入畸形不致命:退化为固定 session_id
        runtime.handle_event(
            AgentEvent(agent=agent, session_id=session_id, kind=event, ts=None, cwd=cwd)
        )
        return {"ok": True}


def _mount_control_routes(app: FastAPI, runtime: Runtime) -> None:
    """挂载原有状态与控制入口。"""

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



def _mount_panel_routes(app: FastAPI, panel: PanelApi | None) -> None:
    """挂载仅允许本机 Web Origin 调用的共享进度入口。"""

    def _guarded(call: Callable[[], dict]) -> dict:
        # 观测性兜底:PanelApi 的意外异常记入 daemon.log 而非裸 500(§7.7)
        try:
            return call()
        except HTTPException:
            raise
        except Exception:
            logger.exception("panel route failed")
            raise HTTPException(status_code=500, detail="panel error") from None

    @app.get("/panel/state")
    def panel_state() -> dict:
        def run() -> dict:
            current = _require_panel(panel).get_progress()
            return {"ok": True, "ready": "error" not in current, "progress": current}

        return _guarded(run)

    @app.get("/panel/next-word")
    def panel_next_word() -> dict:
        return _guarded(lambda: _require_panel(panel).next_word())

    @app.post("/panel/commit")
    def panel_commit(body: PanelCommitIn) -> dict:
        return _guarded(lambda: _require_panel(panel).commit_word(body.result, body.typo_count))

    @app.get("/panel/progress")
    def panel_progress() -> dict:
        return _guarded(lambda: _require_panel(panel).get_progress())


def _require_panel(panel: PanelApi | None) -> PanelApi:
    if panel is None:
        raise HTTPException(status_code=503, detail="panel service unavailable")
    return panel


async def _panel_cors(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """只给 /panel/* 的 localhost/127.0.0.1 浏览器 Origin 开 CORS。"""
    if not request.url.path.startswith("/panel/"):
        return await call_next(request)
    origin = request.headers.get("origin")
    if origin and re.fullmatch(PANEL_ORIGIN_PATTERN, origin) is None:
        return JSONResponse(status_code=403, content={"detail": "origin not allowed"})
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)
    if origin:
        _set_panel_cors_headers(response, origin)
    return response


def _set_panel_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "content-type"
    response.headers.append("Vary", "Origin")


def _reject_browser(request: Request) -> None:
    """带 Origin/Referer 的请求来自浏览器页面(潜在 CSRF),adapter 脚本不会带。"""
    if request.headers.get("origin") or request.headers.get("referer"):
        raise HTTPException(status_code=403, detail="browser requests not allowed")


def _hook_session_id(payload: dict) -> str:
    """为 Codex 子 Agent 使用独立 agent_id,其余事件沿用 session_id。"""
    event_name = str(payload.get("hook_event_name", ""))
    if event_name in ("SubagentStart", "SubagentStop") and payload.get("agent_id"):
        return str(payload["agent_id"])
    return str(payload.get("session_id") or "unknown")
