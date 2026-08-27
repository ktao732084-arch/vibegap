"""Daemon 运行时外壳:持有状态、应用 reducer、执行效果。

全项目唯一的可变状态容器(组合根之外)。daemon 不 import ui(§7.2):
UI 侧通过 Notifier 协议注入,效果在这里翻译成 Notifier 调用。

锁纪律:状态锁内只做状态归约并按转移顺序入队,效果在锁外由首个调用线程
串行排空。通知器很慢时,后续事件只入队即可返回;show/hide 的先后顺序仍稳定。
"""
from __future__ import annotations

import logging
import threading
from collections import deque
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
        self._effect_lock = threading.Lock()
        self._effect_queue: deque[object] = deque()
        self._is_draining_effects = False
        self._sessions = sessions.EMPTY_SESSIONS
        self._sched = scheduler.INITIAL_SCHEDULER

    def handle_event(self, event: AgentEvent) -> None:
        """处理一条 adapter 上报事件;ts 缺省时用注入时钟补齐。"""
        with self._lock:
            event = replace(event, ts=_normalize_timestamp(event.ts, self._clock()))
            key = sessions.SessionKey(event.agent, event.session_id)
            existing = self._sessions.sessions.get(key)
            is_new_run = event.kind is EventKind.RUNNING and (
                existing is None or not existing.is_running
            )
            if is_new_run:
                self._sched, _ = scheduler.on_new_running_event(self._sched)
            self._sessions, finished = sessions.reduce_event(self._sessions, event)
            effects = self._sync_running_state()
            effects += self._apply_finished(finished)
            should_drain = self._queue_effects(effects)
            phase = self._sched.phase.name
        if should_drain:
            self._drain_effects()
        logger.debug("event %s/%s -> phase %s", event.agent.value, event.kind.value, phase)

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
            should_drain = self._queue_effects(effects)
        if should_drain:
            self._drain_effects()

    def word_committed(self) -> None:
        """UI 每提交一个词调用(M2 起使用)。"""
        with self._lock:
            self._sched, effects = scheduler.on_word_committed(
                self._sched,
                self._effective_running(),
                self._clock(),
                timedelta(seconds=self._settings.summary_linger_sec),
            )
            should_drain = self._queue_effects(effects)
        if should_drain:
            self._drain_effects()

    def escape(self) -> None:
        """UI Esc 逃生。"""
        with self._lock:
            self._sched, effects = scheduler.on_escape(self._sched)
            should_drain = self._queue_effects(effects)
        if should_drain:
            self._drain_effects()

    def hotkey_toggle(self) -> None:
        """全局热键手动唤起/隐藏。"""
        with self._lock:
            self._sched, effects = scheduler.on_hotkey_toggle(self._sched)
            should_drain = self._queue_effects(effects)
        if should_drain:
            self._drain_effects()

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

    def _queue_effects(self, effects: list[object]) -> bool:
        """按状态转移顺序入队;返回当前线程是否负责排空。"""
        if not effects:
            return False
        with self._effect_lock:
            self._effect_queue.extend(effects)
            if self._is_draining_effects:
                return False
            self._is_draining_effects = True
            return True

    def _drain_effects(self) -> None:
        """在状态锁外串行执行全部已排队效果。"""
        while True:
            with self._effect_lock:
                if not self._effect_queue:
                    self._is_draining_effects = False
                    return
                effect = self._effect_queue.popleft()
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


def _normalize_timestamp(value: datetime | None, reference: datetime) -> datetime:
    """把 adapter 时间统一到注入时钟的 aware/naive 与时区约定。"""
    if value is None:
        return reference
    if reference.tzinfo is None:
        if value.tzinfo is None:
            return value
        return value.astimezone().replace(tzinfo=None)
    if value.tzinfo is None:
        return value.replace(tzinfo=reference.tzinfo)
    return value.astimezone(reference.tzinfo)
