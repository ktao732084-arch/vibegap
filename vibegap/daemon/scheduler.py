"""UI 调度状态机:决定单词卡何时弹出、何时软关闭。纯函数,时钟由外部注入(§7.3)。

状态图见 spec §4.3:
HIDDEN → ARMED →(延迟到)→ SHOWING →(AgentFinished)→ SOFT_CLOSING →(词提交)→ SUMMARY → HIDDEN
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum, auto

from vibegap.daemon.events import AgentFinished

Effect = object  # 效果的公共基:下方各 frozen dataclass


class Phase(Enum):
    HIDDEN = auto()
    ARMED = auto()          # 有 agent 在跑,延迟计时中,窗口未显示
    SHOWING = auto()
    SOFT_CLOSING = auto()   # 收到 finished,横幅提示,等当前词完成
    SUMMARY = auto()        # 小结页短暂停留


@dataclass(frozen=True)
class ShowWindow:
    pass


@dataclass(frozen=True)
class HideWindow:
    pass


@dataclass(frozen=True)
class ShowBanner:
    finished: AgentFinished


@dataclass(frozen=True)
class ClearBanner:
    pass


@dataclass(frozen=True)
class ShowSummary:
    pass


@dataclass(frozen=True)
class SchedulerState:
    phase: Phase = Phase.HIDDEN
    armed_at: datetime | None = None
    summary_until: datetime | None = None
    banner: AgentFinished | None = None
    # Esc 抑制:用户手动隐藏后,同一批运行中的会话不得再次唤起窗口。
    # 新的 RUNNING 事件(用户又提了问)或全部会话结束时解除。
    suppressed: bool = False


INITIAL_SCHEDULER = SchedulerState()


def on_running_changed(
    state: SchedulerState, is_any_running: bool, now: datetime
) -> tuple[SchedulerState, list[Effect]]:
    """会话层运行状态同步(每 tick 调用,水平触发)。"""
    if is_any_running and state.phase is Phase.HIDDEN and not state.suppressed:
        return replace(state, phase=Phase.ARMED, armed_at=now), []
    if not is_any_running:
        if state.phase is Phase.ARMED:
            return SchedulerState(), []  # 任务在延迟期内就结束了:静默取消,零打扰
        if state.suppressed:
            return replace(state, suppressed=False), []  # 全部会话结束,解除 Esc 抑制
    return state, []


def on_new_running_event(state: SchedulerState) -> tuple[SchedulerState, list[Effect]]:
    """收到新的 RUNNING 事件(用户又提了问):解除 Esc 抑制。"""
    if state.suppressed:
        return replace(state, suppressed=False), []
    return state, []


def on_tick(
    state: SchedulerState,
    now: datetime,
    is_any_running: bool,
    popup_delay: timedelta,
) -> tuple[SchedulerState, list[Effect]]:
    """定时器脉冲:处理 ARMED 延迟到期与 SUMMARY 停留到期。"""
    if state.phase is Phase.ARMED and state.armed_at is not None:
        if now - state.armed_at >= popup_delay:
            return replace(state, phase=Phase.SHOWING, armed_at=None), [ShowWindow()]
    if state.phase is Phase.SUMMARY and state.summary_until is not None:
        if now >= state.summary_until:
            if is_any_running:
                # 小结期间又有新任务在跑:收起后重新进入延迟计时
                return SchedulerState(phase=Phase.ARMED, armed_at=now), [HideWindow()]
            return SchedulerState(), [HideWindow()]
    return state, []


def on_agent_finished(
    state: SchedulerState, finished: AgentFinished, is_any_running: bool
) -> tuple[SchedulerState, list[Effect]]:
    """某 agent 跑完/等确认。SHOWING 转软关闭;ARMED 视 any_running 决定去留。"""
    if state.phase is Phase.ARMED:
        if is_any_running:
            return state, []
        return SchedulerState(), []
    if state.phase in (Phase.SHOWING, Phase.SOFT_CLOSING):
        new_state = replace(state, phase=Phase.SOFT_CLOSING, banner=finished)
        return new_state, [ShowBanner(finished)]
    return state, []


def on_word_committed(
    state: SchedulerState,
    is_any_running: bool,
    now: datetime,
    summary_linger: timedelta,
) -> tuple[SchedulerState, list[Effect]]:
    """UI 每提交一个词调用一次;只在 SOFT_CLOSING 阶段驱动转移。"""
    if state.phase is not Phase.SOFT_CLOSING:
        return state, []
    if is_any_running:
        # 用户没理会横幅继续背,且还有别的会话在跑:清横幅回到正常背词
        return replace(state, phase=Phase.SHOWING, banner=None), [ClearBanner()]
    new_state = replace(
        state, phase=Phase.SUMMARY, banner=None, summary_until=now + summary_linger
    )
    return new_state, [ShowSummary()]


def on_escape(state: SchedulerState) -> tuple[SchedulerState, list[Effect]]:
    """Esc 逃生:立即隐藏,并抑制同一批运行会话再次唤起(spec §4.3)。"""
    if state.phase is Phase.HIDDEN:
        return state, []
    return SchedulerState(suppressed=True), [HideWindow()]


def on_hotkey_toggle(
    state: SchedulerState,
) -> tuple[SchedulerState, list[Effect]]:
    """全局热键:HIDDEN/ARMED → 立即显示;其余 → 隐藏。与 agent 状态无关。"""
    if state.phase in (Phase.HIDDEN, Phase.ARMED):
        return SchedulerState(phase=Phase.SHOWING), [ShowWindow()]
    # 手动隐藏和 Esc 语义一致:同一批仍在运行的会话不能在下个 tick 又弹回。
    return SchedulerState(suppressed=True), [HideWindow()]
