"""Runtime 外壳集成测试:假时钟 + 假通知器,验证事件→效果全链路。"""
from datetime import datetime, timedelta

from vibegap.config import Settings
from vibegap.daemon.events import Agent, AgentEvent, AgentFinished, EventKind
from vibegap.daemon.runtime import Runtime

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


def test_slow_notifier_does_not_block_event_handling():
    # review HIGH-1 回归锁:效果在锁外执行,慢通知器(如 toast 子进程)不得阻塞钩子事件
    import threading
    import time as _time

    class SlowNotifier(FakeNotifier):
        def show_window(self):
            super().show_window()
            _time.sleep(0.5)

    clock = FakeClock()
    runtime = Runtime(settings=SETTINGS, notifier=SlowNotifier(), clock=clock)
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    clock.advance(20)
    tick_thread = threading.Thread(target=runtime.tick)  # 触发 show_window,慢 0.5s
    tick_thread.start()
    _time.sleep(0.1)  # 此刻 tick 已释放锁、正卡在慢效果里
    start = _time.perf_counter()
    runtime.handle_event(_event(EventKind.DONE, clock=clock))
    elapsed = _time.perf_counter() - start
    tick_thread.join()
    assert elapsed < 0.3, f"event blocked {elapsed:.2f}s by slow notifier"
    assert runtime.snapshot().phase == "SOFT_CLOSING"


def test_event_without_ts_uses_injected_clock():
    runtime, _, clock = _make()
    runtime.handle_event(AgentEvent(Agent.CLAUDE_CODE, "s1", EventKind.RUNNING, ts=None))
    clock.advance(31 * 60)
    runtime.tick()  # 若 ts 落在假时钟上,TTL 清理应生效
    assert runtime.snapshot().session_count == 0


def test_auto_popup_off_never_arms_but_hotkey_still_works():
    clock = FakeClock()
    notifier = FakeNotifier()
    runtime = Runtime(
        settings=Settings(popup_delay_sec=18, auto_popup=False),
        notifier=notifier,
        clock=clock,
    )
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    clock.advance(60)
    runtime.tick()
    assert notifier.calls == []  # 关闭自动唤醒:任务再久也不弹
    assert runtime.snapshot().phase == "HIDDEN"
    runtime.hotkey_toggle()
    assert notifier.calls == [("show_window",)]  # 手动唤醒不受影响


def test_auto_popup_off_finished_while_manual_showing_still_banners():
    clock = FakeClock()
    notifier = FakeNotifier()
    runtime = Runtime(
        settings=Settings(auto_popup=False), notifier=notifier, clock=clock
    )
    runtime.handle_event(_event(EventKind.RUNNING, clock=clock))
    runtime.hotkey_toggle()  # 手动打开着背单词
    runtime.handle_event(_event(EventKind.DONE, clock=clock))
    assert ("show_banner", "claude-code", "done") in notifier.calls


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
