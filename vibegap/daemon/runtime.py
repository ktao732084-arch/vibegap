"""Daemon 运行时外壳:持有状态、应用 reducer、执行效果。

全项目唯一的可变状态容器(组合根之外)。daemon 不 import ui(§7.2):
UI 侧通过 Notifier 协议注入,效果在这里翻译成 Notifier 调用。

锁纪律:锁内只做状态归约,效果一律在锁外执行——通知器可能很慢(toast 子进程)
甚至回调回 Runtime,锁内执行会阻塞钩子上报乃至死锁。代价是极端并发下
效果执行顺序可能与状态转移顺序有微小偏差,对幂等的 UI 操作无害。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Callable, Protocol

from vibegap.config import Settings
from vibegap.daemon import scheduler, sessions
from vibegap.daemon.events import AgentEvent, AgentFinished, EventKind
from vibegap.daemon.scheduler import (
    ClearBanner,
    HideWindow,
    ShowBanner,
    ShowSummary,
    ShowWindow,
)

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    """UI 侧注入的效果执行器(M1 为 toast/日志占位,M2 换悬浮窗)。"""

    def show_window(self) -> None: ...
    def hide_window(self) -> None: ...
    def show_banner(self, finished: AgentFinished) -> None: ...
    def clear_banner(self) -> None: ...
    def show_summary(self) -> None: ...


@dataclass(frozen=True)
class SessionView:
    """会话面板展示用的单条会话视图。"""

    agent: str
    session_id: str
    is_running: bool
    last_event_at: str  # ISO 字符串
    cwd: str


@dataclass(frozen=True)
class RuntimeSnapshot:
    """GET /state 与 UI 状态栏用的只读快照。"""

    phase: str
    session_count: int
    is_any_running: bool
    running_agents: tuple[str, ...] = ()  # 有运行中会话的 agent 名,去重有序
    sessions: tuple[SessionView, ...] = ()


class Runtime:
    """事件入口与定时脉冲的汇聚点;内部用锁保证串行。"""

    def __init__(
        self,
        settings: Settings,
        notifier: Notifier,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._settings = settings
        self._notifier = notifier
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions = sessions.EMPTY_SESSIONS
        self._sched = scheduler.INITIAL_SCHEDULER

    def handle_event(self, event: AgentEvent) -> None:
        """处理一条 adapter 上报事件;ts 缺省时用注入时钟补齐。"""
        with self._lock:
            if event.ts is None:
                event = replace(event, ts=self._clock())
            if event.kind is EventKind.RUNNING:
                self._sched, _ = scheduler.on_new_running_event(self._sched)
            self._sessions, finished = sessions.reduce_event(self._sessions, event)
            effects = self._sync_running_state()
            effects += self._apply_finished(finished)
        self._run_effects(effects)
        logger.debug("event %s/%s -> phase %s", event.agent.value, event.kind.value, self._sched.phase.name)

    def tick(self) -> None:
        """定时脉冲:孤儿会话清理 + 延迟弹出/小结到期。"""
        with self._lock:
            now = self._clock()
            ttl = timedelta(minutes=self._settings.session_ttl_min)
            self._sessions = sessions.cleanup_expired(self._sessions, now, ttl)
            effects = self._sync_running_state()
            self._sched, eff = scheduler.on_tick(
                self._sched,
                now,
                self._effective_running(),
                timedelta(seconds=self._settings.popup_delay_sec),
            )
            effects += eff
        self._run_effects(effects)

    def word_committed(self) -> None:
        """UI 每提交一个词调用(M2 起使用)。"""
        with self._lock:
            self._sched, effects = scheduler.on_word_committed(
                self._sched,
                self._effective_running(),
                self._clock(),
                timedelta(seconds=self._settings.summary_linger_sec),
            )
        self._run_effects(effects)

    def escape(self) -> None:
        """UI Esc 逃生。"""
        with self._lock:
            self._sched, effects = scheduler.on_escape(self._sched)
        self._run_effects(effects)

    def hotkey_toggle(self) -> None:
        """全局热键手动唤起/隐藏。"""
        with self._lock:
            self._sched, effects = scheduler.on_hotkey_toggle(self._sched)
        self._run_effects(effects)

    def update_settings(self, settings: Settings) -> None:
        """设置热更新(设置面板改弹出延迟等时调用)。"""
        with self._lock:
            self._settings = settings

    def snapshot(self) -> RuntimeSnapshot:
        """当前状态只读快照(调试端点与 UI 状态栏用)。"""
        with self._lock:
            running = []
            views = []
            for key, info in sorted(
                self._sessions.sessions.items(),
                key=lambda kv: kv[1].last_event_at,
                reverse=True,
            ):
                if info.is_running and key.agent.value not in running:
                    running.append(key.agent.value)
                views.append(
                    SessionView(
                        agent=key.agent.value,
                        session_id=key.session_id,
                        is_running=info.is_running,
                        last_event_at=info.last_event_at.isoformat(timespec="seconds"),
                        cwd=info.cwd,
                    )
                )
            return RuntimeSnapshot(
                phase=self._sched.phase.name,
                session_count=len(self._sessions.sessions),
                is_any_running=sessions.any_running(self._sessions),
                running_agents=tuple(running),
                sessions=tuple(views),
            )

    def _effective_running(self) -> bool:
        """调度器眼中的 any_running:自动唤醒关闭时恒为 False(只可手动唤起)。"""
        return self._settings.auto_popup and sessions.any_running(self._sessions)

    def _sync_running_state(self) -> list[object]:
        self._sched, effects = scheduler.on_running_changed(
            self._sched, self._effective_running(), self._clock()
        )
        return list(effects)

    def _apply_finished(self, finished: list[AgentFinished]) -> list[object]:
        effects: list[object] = []
        is_running = self._effective_running()
        for item in finished:
            self._sched, eff = scheduler.on_agent_finished(self._sched, item, is_running)
            effects += eff
        return effects

    def _run_effects(self, effects: list[object]) -> None:
        for effect in effects:
            self._run_one_effect(effect)

    def _run_one_effect(self, effect: object) -> None:
        try:
            if isinstance(effect, ShowWindow):
                self._notifier.show_window()
            elif isinstance(effect, HideWindow):
                self._notifier.hide_window()
            elif isinstance(effect, ShowBanner):
                self._notifier.show_banner(effect.finished)
            elif isinstance(effect, ClearBanner):
                self._notifier.clear_banner()
            elif isinstance(effect, ShowSummary):
                self._notifier.show_summary()
        except Exception:  # noqa: BLE001 - notifier 故障不能拖垮状态机
            logger.exception("notifier failed on %s", type(effect).__name__)
