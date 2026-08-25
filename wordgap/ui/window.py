"""pywebview 悬浮窗管理:置顶、显示/隐藏、位置记忆、效果转发到 JS Shell。

实现 daemon.runtime.Notifier 协议。窗口对象在 webview 主循环启动后注入
(set_window),之前收到的效果按"最后状态"缓存,注入时补放。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from wordgap.config import WINDOW_HEIGHT, WINDOW_TITLE, WINDOW_WIDTH
from wordgap.daemon.events import AgentFinished, EventKind

logger = logging.getLogger(__name__)

WEB_INDEX = Path(__file__).resolve().parent / "web" / "index.html"
_POS_KEY = "window_pos"


class WindowNotifier:
    """把调度器效果翻译成窗口操作 + JS 调用。"""

    def __init__(self, fallback=None) -> None:
        self._window = None
        self._fallback = fallback  # 窗口未就绪时的兜底通知器(如 ToastNotifier)
        self._pending_show = False

    def set_window(self, window) -> None:
        self._window = window
        if self._pending_show:
            self._pending_show = False
            self.show_window()

    def show_window(self) -> None:
        if self._window is None:
            self._pending_show = True
            if self._fallback:
                self._fallback.show_window()
            return
        self._js("shell.onShow()")
        self._window.show()

    def hide_window(self) -> None:
        if self._window is None:
            self._pending_show = False
            return
        self._js("shell.onReset()")
        self._window.hide()

    def show_banner(self, finished: AgentFinished) -> None:
        if self._window is None:
            if self._fallback:
                self._fallback.show_banner(finished)
            return
        payload = json.dumps(
            {
                "agent": finished.agent.value,
                "kind": finished.kind.value,
                "waiting": finished.kind is EventKind.ATTENTION,
            },
            ensure_ascii=False,
        )
        self._js(f"shell.onAgentFinished({payload})")

    def clear_banner(self) -> None:
        self._js("shell.onClearBanner()")

    def show_summary(self) -> None:
        self._js("shell.onSummary()")

    def _js(self, code: str) -> None:
        if self._window is None:
            return
        try:
            self._window.evaluate_js(f"window.shell && {code}")
        except Exception as exc:  # noqa: BLE001 - 窗口销毁竞态等,不拖垮 runtime
            logger.warning("evaluate_js failed: %s", exc)


def create_window(bridge, kv_get, kv_set):
    """创建悬浮窗(隐藏启动);kv_get/kv_set 注入以记忆窗口位置。"""
    import webview

    x, y = _load_pos(kv_get)
    window = webview.create_window(
        WINDOW_TITLE,
        url=str(WEB_INDEX),
        js_api=bridge,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        x=x,
        y=y,
        frameless=True,
        easy_drag=True,
        on_top=True,
        hidden=True,
        focus=False,
    )
    if hasattr(window.events, "moved"):
        window.events.moved += lambda x, y: _save_pos(kv_set, x, y)
    return window


def _load_pos(kv_get) -> tuple[int | None, int | None]:
    try:
        raw = kv_get(_POS_KEY)
        if raw:
            pos = json.loads(raw)
            return int(pos["x"]), int(pos["y"])
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("bad saved window pos: %s", exc)
    return None, None


def _save_pos(kv_set, x: int, y: int) -> None:
    try:
        kv_set(_POS_KEY, json.dumps({"x": int(x), "y": int(y)}))
    except Exception as exc:  # noqa: BLE001 - 位置记忆失败无关紧要
        logger.warning("save window pos failed: %s", exc)
