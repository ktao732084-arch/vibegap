"""Runtime 外壳集成测试:假时钟 + 假通知器,验证事件→效果全链路。"""
from datetime import datetime, timedelta

from wordgap.config import Settings
from wordgap.daemon.events import Agent, AgentEvent, AgentFinished, EventKind
from wordgap.daemon.runtime import Runtime

T0 = datetime(2026, 8, 25, 10, 0, 0)
SETTINGS = Settings(popup_delay_sec=18, summary_linger_sec=2, session_ttl_min=30)


class FakeClock:
    def __init__(self, start: datetime = T0):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeNotifier:
    def __init__(self):
        self.calls: list[tuple] = []

    def show_window(self):
        self.calls.append(("show_window",))

    def hide_window(self):
        self.calls.append(("hide_window",))

    def show_banner(self, finished: AgentFinished):
        self.calls.append(("show_banner", finished.agent.value, finished.kind.value))

    def clear_banner(self):
        self.calls.append(("clear_banner",))

    def show_summary(self):
        self.calls.append(("show_summary",))


def _make():
    clock = FakeClock()
    notifier = FakeNotifier()
    runtime = Runtime(settings=SETTINGS, notifier=notifier, clock=clock)
    return runtime, notifier, clock


def _event(kind: EventKind, agent=Agent.CLAUDE_CODE, sid="s1", ts=None, clock=None):
    return AgentEvent(agent=agent, session_id=sid, kind=kind, ts=ts or (clock.now if clock else T0))


def test_slow_task_pops_after_delay():
    runtime, notifier, clock = _make()
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    clock.advance(17)
    runtime.tick()
    assert notifier.calls == []  # 延迟未到
    clock.advance(2)
    runtime.tick()
    assert notifier.calls == [("show_window",)]
    assert runtime.snapshot().phase == "SHOWING"


def test_fast_task_never_shows_anything():
    runtime, notifier, clock = _make()
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    clock.advance(5)
    runtime.handle_event(_event(EventKind.DONE, clock=clock))
    clock.advance(60)
    runtime.tick()
    assert notifier.calls == []  # 防闪弹:全程零打扰
    assert runtime.snapshot().phase == "HIDDEN"


def test_finished_while_showing_banners_then_summary_then_hides():
    runtime, notifier, clock = _make()
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    clock.advance(20)
    runtime.tick()
    runtime.handle_event(_event(EventKind.DONE, clock=clock))
    assert ("show_banner", "claude-code", "done") in notifier.calls
    runtime.word_committed()
    assert ("show_summary",) in notifier.calls
    clock.advance(3)
    runtime.tick()
    assert notifier.calls[-1] == ("hide_window",)
    assert runtime.snapshot().phase == "HIDDEN"


def test_attention_banner_wording_kind():
    runtime, notifier, clock = _make()
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    clock.advance(20)
    runtime.tick()
    runtime.handle_event(_event(EventKind.ATTENTION, clock=clock))
    assert ("show_banner", "claude-code", "attention") in notifier.calls


def test_multi_agent_commit_resumes_when_other_still_running():
    runtime, notifier, clock = _make()
    runtime.handle_event(_event(EventKind.RUNNING, sid="a", clock=clock))
    runtime.handle_event(_event(EventKind.RUNNING, agent=Agent.CODEX, sid="b", clock=clock))
    clock.advance(20)
    runtime.tick()
    runtime.handle_event(_event(EventKind.DONE, sid="a", clock=clock))
    runtime.word_committed()
    assert notifier.calls[-1] == ("clear_banner",)  # codex 还在跑,回到继续背词
    assert runtime.snapshot().phase == "SHOWING"


def test_orphan_session_cleanup_via_tick():
    runtime, notifier, clock = _make()
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    clock.advance(31 * 60)
    runtime.tick()
    snap = runtime.snapshot()
    assert snap.session_count == 0
    assert not snap.is_any_running
    assert snap.phase in ("HIDDEN", "SHOWING")  # 已弹出的窗口不因清理强关


def test_escape_and_hotkey_paths():
    runtime, notifier, clock = _make()
    runtime.hotkey_toggle()
    assert notifier.calls == [("show_window",)]
    runtime.escape()
    assert notifier.calls[-1] == ("hide_window",)


def test_notifier_failure_does_not_break_runtime():
    class BrokenNotifier(FakeNotifier):
        def show_window(self):
            raise RuntimeError("boom")

    clock = FakeClock()
    runtime = Runtime(settings=SETTINGS, notifier=BrokenNotifier(), clock=clock)
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    clock.advance(20)
    runtime.tick()  # 不应抛异常
    assert runtime.snapshot().phase == "SHOWING"
