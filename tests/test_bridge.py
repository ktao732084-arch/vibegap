"""Bridge 单测:文件库 + 真 Runtime(假通知器),覆盖 UI 数据出口。"""
from datetime import timedelta

import pytest

from wordgap.config import Settings
from wordgap.daemon.newsfeed import NewsFeed, NewsItem
from wordgap.daemon.runtime import Runtime
from wordgap.store.db import connect
from wordgap.store.wordbooks import import_wordbook, set_current
from wordgap.ui.bridge import open_bridge
from tests.test_runtime import FakeClock, FakeNotifier

WORDS = [{"name": f"word{i}", "trans": [f"释义{i}"], "usphone": "x"} for i in range(5)]
ITEM = NewsItem(title="新闻", url="u", source="s", summary="", published_at="")


@pytest.fixture
def env(tmp_path):
    db_path = tmp_path / "t.db"
    conn = connect(db_path)
    book = import_wordbook(conn, "test", WORDS, mode="sequential")
    set_current(conn, book.id)
    conn.close()
    clock = FakeClock()
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=clock)
    feed = NewsFeed(fetcher=lambda: [ITEM], clock=clock, refresh_interval=timedelta(minutes=1))
    bridge = open_bridge(db_path, runtime, feed)
    yield bridge, runtime, feed
    bridge._close()


def test_next_word_and_commit_flow(env):
    bridge, _, _ = env
    w = bridge.next_word()
    assert w["name"] == "word0"
    assert w["trans"] == ["释义0"]
    assert w["total"] == 5
    result = bridge.commit_word("pass", 1)
    assert result["cursor"] == 1
    assert bridge.next_word()["name"] == "word1"


def test_progress_summary(env):
    bridge, _, _ = env
    bridge.commit_word("pass")
    p = bridge.get_progress()
    assert p["cursor"] == 1
    assert p["book_name"] == "test"
    assert p["mode"] == "sequential"


def test_commit_invalid_result_returns_error(env):
    bridge, _, _ = env
    assert "error" in bridge.commit_word("bogus")


def test_no_wordbook_error(tmp_path):
    db_path = tmp_path / "empty.db"
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=FakeClock())
    bridge = open_bridge(db_path, runtime, NewsFeed(fetcher=lambda: []))
    assert bridge.next_word() == {"error": "no_wordbook"}
    assert bridge.commit_word("pass") == {"error": "no_wordbook"}
    assert "error" in bridge.get_progress()
    bridge._close()


def test_get_news(env):
    bridge, _, feed = env
    assert bridge.get_news() == []
    feed.maybe_refresh(blocking=True)
    news = bridge.get_news()
    assert news == [{"title": "新闻", "source": "s", "url": "u", "published_at": ""}]


def test_get_state_running_agents(env):
    bridge, runtime, _ = env
    from wordgap.daemon.events import Agent, AgentEvent, EventKind

    assert bridge.get_state()["running_agents"] == []
    runtime.handle_event(AgentEvent(Agent.CODEX, "a", EventKind.RUNNING, ts=None))
    runtime.handle_event(AgentEvent(Agent.CLAUDE_CODE, "b", EventKind.RUNNING, ts=None))
    state = bridge.get_state()
    assert sorted(state["running_agents"]) == ["claude-code", "codex"]
    assert state["any_running"] is True


def test_escape_drives_runtime(env):
    bridge, runtime, _ = env
    runtime.hotkey_toggle()  # SHOWING
    bridge.escape()
    assert runtime.snapshot().phase == "HIDDEN"


def test_commit_word_during_soft_close_reaches_summary(env):
    bridge, runtime, _ = env
    from wordgap.daemon.events import Agent, AgentEvent, EventKind

    runtime.handle_event(AgentEvent(Agent.CODEX, "s", EventKind.RUNNING, ts=None))
    runtime.hotkey_toggle()  # 直接显示
    runtime.handle_event(AgentEvent(Agent.CODEX, "s", EventKind.DONE, ts=None))
    assert runtime.snapshot().phase == "SOFT_CLOSING"
    bridge.commit_word("pass")
    assert runtime.snapshot().phase == "SUMMARY"