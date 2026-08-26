"""UI 调度状态机单测(虚拟时钟)。"""
from datetime import datetime, timedelta

from vibegap.daemon.events import Agent, AgentFinished, EventKind
from vibegap.daemon.scheduler import (
    INITIAL_SCHEDULER,
    ClearBanner,
    HideWindow,
    Phase,
    ShowBanner,
    ShowSummary,
    ShowWindow,
    on_agent_finished,
    on_escape,
    on_hotkey_toggle,
    on_running_changed,
    on_tick,
    on_word_committed,
)

T0 = datetime(2026, 8, 25, 10, 0, 0)
DELAY = timedelta(seconds=18)
LINGER = timedelta(seconds=2)
FINISHED = AgentFinished(agent=Agent.CODEX, kind=EventKind.DONE)


def _armed():
    state, _ = on_running_changed(INITIAL_SCHEDULER, True, T0)
    return state


def _showing():
    state, _ = on_tick(_armed(), T0 + DELAY, True, DELAY)
    return state


def _soft_closing():
    state, _ = on_agent_finished(_showing(), FINISHED, False)
    return state


def test_running_arms_without_showing():
    state = _armed()
    assert state.phase is Phase.ARMED


def test_tick_before_delay_stays_hidden():
    state, effects = on_tick(_armed(), T0 + DELAY - timedelta(seconds=1), True, DELAY)
    assert state.phase is Phase.ARMED
    assert effects == []


def test_tick_after_delay_shows_window():
    state, effects = on_tick(_armed(), T0 + DELAY, True, DELAY)
    assert state.phase is Phase.SHOWING
    assert effects == [ShowWindow()]


def test_fast_task_cancels_silently():
    # 延迟期内任务结束:静默取消,无任何 UI 效果(防闪弹核心规则)
    state, effects = on_running_changed(_armed(), False, T0 + timedelta(seconds=5))
    assert state.phase is Phase.HIDDEN
    assert effects == []


def test_finished_while_armed_and_nothing_running_cancels():
    state, effects = on_agent_finished(_armed(), FINISHED, False)
    assert state.phase is Phase.HIDDEN
    assert effects == []


def test_finished_while_armed_but_others_running_keeps_armed():
    state, effects = on_agent_finished(_armed(), FINISHED, True)
    assert state.phase is Phase.ARMED
    assert effects == []


def test_finished_during_armed_is_intentionally_dropped():
    # spec §4.3 规则 5:延迟期内 A 完成、B 仍在跑,之后窗口因 B 弹出时不补报 A 的横幅
    state, _ = on_agent_finished(_armed(), FINISHED, True)
    state, effects = on_tick(state, T0 + DELAY, True, DELAY)
    assert state.phase is Phase.SHOWING
    assert state.banner is None
    assert effects == [ShowWindow()]


def test_running_changed_is_noop_while_showing():
    state, effects = on_running_changed(_showing(), True, T0)
    assert state.phase is Phase.SHOWING
    assert effects == []
    state, effects = on_running_changed(_showing(), False, T0)
    assert state.phase is Phase.SHOWING  # SHOWING 只因 finished/Esc/热键退出
    assert effects == []


def test_agent_finished_is_noop_while_hidden_or_summary():
    state, effects = on_agent_finished(INITIAL_SCHEDULER, FINISHED, False)
    assert state.phase is Phase.HIDDEN
    assert effects == []
    summary_state, _ = on_word_committed(_soft_closing(), False, T0, LINGER)
    state, effects = on_agent_finished(summary_state, FINISHED, False)
    assert state.phase is Phase.SUMMARY
    assert effects == []


def test_finished_while_showing_soft_closes_with_banner():
    state, effects = on_agent_finished(_showing(), FINISHED, False)
    assert state.phase is Phase.SOFT_CLOSING
    assert effects == [ShowBanner(FINISHED)]
    assert state.banner == FINISHED


def test_word_commit_in_soft_closing_goes_to_summary_then_hides():
    state, effects = on_word_committed(_soft_closing(), False, T0, LINGER)
    assert state.phase is Phase.SUMMARY
    assert effects == [ShowSummary()]
    state, effects = on_tick(state, T0 + LINGER, False, DELAY)
    assert state.phase is Phase.HIDDEN
    assert effects == [HideWindow()]


def test_word_commit_in_soft_closing_resumes_if_others_running():
    state, effects = on_word_committed(_soft_closing(), True, T0, LINGER)
    assert state.phase is Phase.SHOWING
    assert state.banner is None
    assert effects == [ClearBanner()]


def test_summary_expiry_rearms_if_new_task_running():
    state, _ = on_word_committed(_soft_closing(), False, T0, LINGER)
    state, effects = on_tick(state, T0 + LINGER, True, DELAY)
    assert state.phase is Phase.ARMED
    assert effects == [HideWindow()]


def test_normal_word_commit_while_showing_is_noop():
    state, effects = on_word_committed(_showing(), True, T0, LINGER)
    assert state.phase is Phase.SHOWING
    assert effects == []


def test_escape_suppresses_rearm_while_same_sessions_running():
    # 用户 Esc 后,同一批运行中的会话不得把窗口再弹回来(真机发现的缺陷)
    state, _ = on_escape(_showing())
    assert state.suppressed
    state, effects = on_running_changed(state, True, T0)  # 每 tick 的水平触发
    assert state.phase is Phase.HIDDEN
    assert effects == []
    state, effects = on_tick(state, T0 + DELAY * 10, True, DELAY)
    assert state.phase is Phase.HIDDEN  # 永不再弹


def test_new_running_event_clears_suppression():
    from vibegap.daemon.scheduler import on_new_running_event

    state, _ = on_escape(_showing())
    state, _ = on_new_running_event(state)  # 用户又提了问
    assert not state.suppressed
    state, _ = on_running_changed(state, True, T0)
    assert state.phase is Phase.ARMED


def test_all_sessions_ending_clears_suppression():
    state, _ = on_escape(_showing())
    state, _ = on_running_changed(state, False, T0)  # 全部会话结束
    assert not state.suppressed
    state, _ = on_running_changed(state, True, T0)  # 新任务:恢复正常弹出
    assert state.phase is Phase.ARMED


def test_escape_hides_from_any_visible_phase():
    for state in (_showing(), _soft_closing()):
        new_state, effects = on_escape(state)
        assert new_state.phase is Phase.HIDDEN
        assert effects == [HideWindow()]


def test_escape_while_hidden_is_noop():
    state, effects = on_escape(INITIAL_SCHEDULER)
    assert state.phase is Phase.HIDDEN
    assert effects == []


def test_hotkey_toggles_show_and_hide():
    state, effects = on_hotkey_toggle(INITIAL_SCHEDULER)
    assert state.phase is Phase.SHOWING
    assert effects == [ShowWindow()]
    state, effects = on_hotkey_toggle(state)
    assert state.phase is Phase.HIDDEN
    assert effects == [HideWindow()]


def test_hotkey_while_armed_shows_immediately():
    state, effects = on_hotkey_toggle(_armed())
    assert state.phase is Phase.SHOWING
    assert effects == [ShowWindow()]
