"""Bridge 单测:文件库 + 真 Runtime(假通知器),覆盖 UI 数据出口。"""
from datetime import timedelta

import pytest

from vibegap.config import Settings
from vibegap.daemon.newsfeed import NewsFeed, NewsItem
from vibegap.daemon.runtime import Runtime
from vibegap.store.db import connect
from vibegap.store.wordbooks import import_wordbook, set_current
from vibegap.ui.bridge import open_bridge
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


def test_peek_word_browsing(env):
    bridge, _, _ = env
    bridge.commit_word("pass")  # cursor=1
    assert bridge.peek_word(-1)["name"] == "word0"
    assert bridge.peek_word(0)["name"] == "word1"
    assert bridge.peek_word(1)["name"] == "word2"
    assert bridge.peek_word(-2) == {"error": "out_of_range"}
    assert bridge.peek_word(99) == {"error": "out_of_range"}
    # 浏览不动游标
    assert bridge.get_progress()["cursor"] == 1


def test_book_switching(env):
    bridge, _, _ = env
    from vibegap.store.db import connect as _connect
    books = bridge.list_books()
    assert books[0]["current"] is True
    assert bridge.set_book(9999) == {"error": "wordbook 9999 not found"}


def test_review_flow(env):
    bridge, _, _ = env
    bridge.commit_word("fail", 2)   # word0 错
    bridge.commit_word("pass")      # word1 对
    bridge.commit_word("skip")      # word2 跳过
    queue = bridge.get_review()
    assert [w["name"] for w in queue] == ["word0", "word2"]
    assert bridge.log_review(queue[0]["word_index"], "pass") == {"ok": True}
    assert queue[0]["word_index"] not in [
        w["word_index"] for w in bridge.get_review()
    ]  # 复习通过后移出队列
    assert "error" in bridge.log_review(999, "pass")
    assert "error" in bridge.log_review(0, "bogus")


def test_daily_goal_in_progress(env):
    bridge, _, _ = env
    p = bridge.get_progress()
    assert p["goal"] == 50
    assert p["today"] == 0
    bridge.commit_word("pass")
    assert bridge.get_progress()["today"] == 1


def test_get_state_session_counts_and_cwd(env):
    bridge, runtime, _ = env
    from vibegap.daemon.events import Agent, AgentEvent, EventKind

    runtime.handle_event(
        AgentEvent(Agent.CODEX, "a", EventKind.RUNNING, ts=None, cwd="E:/proj")
    )
    runtime.handle_event(AgentEvent(Agent.CODEX, "b", EventKind.RUNNING, ts=None))
    runtime.handle_event(AgentEvent(Agent.CODEX, "b", EventKind.DONE, ts=None))
    state = bridge.get_state()
    assert state["active_count"] == 1
    assert state["done_count"] == 1
    by_id = {s["session_id"]: s for s in state["sessions"]}
    assert by_id["a"]["cwd"] == "E:/proj"
    assert by_id["a"]["running"] is True
    assert by_id["b"]["running"] is False


def test_prefs_roundtrip(env):
    bridge, _, _ = env
    assert bridge.get_prefs() == {"auto_pronounce": True, "theme": "auto"}  # 默认
    assert bridge.set_pref("auto_pronounce", False) == {"ok": True}
    assert bridge.set_pref("theme", "light") == {"ok": True}
    assert bridge.get_prefs() == {"auto_pronounce": False, "theme": "light"}
    assert bridge.set_pref("theme", "neon") == {"error": "bad_value"}
    assert bridge.set_pref("evil_key", True) == {"error": "bad_key"}


def test_settings_roundtrip(tmp_path):
    from vibegap.config import Settings
    from vibegap.daemon.newsfeed import NewsFeed
    from vibegap.daemon.runtime import Runtime
    from vibegap.ui.bridge import Bridge
    import json as _json

    db_path = tmp_path / "t.db"
    from vibegap.store.db import connect as _connect
    conn = _connect(db_path)
    book = import_wordbook(conn, "t", WORDS, mode="shuffled", seed=1)
    set_current(conn, book.id)
    conn.close()
    cfg = tmp_path / "config.json"
    runtime = Runtime(settings=Settings(), notifier=FakeNotifier(), clock=FakeClock())
    bridge = Bridge(db_path, runtime, NewsFeed(fetcher=lambda: []), Settings(), config_path=cfg)

    s = bridge.get_settings()
    assert s == {
        "popup_delay_sec": 18,
        "daily_goal": 50,
        "auto_popup": True,
        "hotkey": "",  # 测试环境不启动热键线程
        "mode": "shuffled",
    }
    assert bridge.set_setting("daily_goal", 80) == {"ok": True, "value": 80}
    assert bridge.set_setting("popup_delay_sec", 999) == {"ok": True, "value": 120}  # 夹到上限
    assert bridge.set_setting("nope", 1) == {"error": "bad_key"}
    assert bridge.get_settings()["daily_goal"] == 80
    saved = _json.loads(cfg.read_text(encoding="utf-8"))
    assert saved == {"daily_goal": 80, "popup_delay_sec": 120}  # 持久化到 config.json
    assert bridge.set_book_mode("sequential") == {"ok": True}
    assert bridge.get_settings()["mode"] == "sequential"
    assert "error" in bridge.set_book_mode("bogus")
    bridge._close()


def test_get_agents_reports_all_five(env):
    bridge, _, _ = env
    agents = bridge.get_agents()
    assert [a["agent"] for a in agents] == ["claude-code", "codex", "workbuddy", "pi", "dsh"]
    for a in agents:
        assert a["status"] in ("connected", "available", "manual", "missing")
        assert a["detail"]


def test_install_agent_rejects_unknown(env):
    bridge, _, _ = env
    assert bridge.install_agent("skynet") == {"error": "unsupported_agent"}
    assert bridge.uninstall_agent("skynet") == {"error": "unsupported_agent"}


def test_get_state_running_agents(env):
    bridge, runtime, _ = env
    from vibegap.daemon.events import Agent, AgentEvent, EventKind

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


def test_escape_skips_current_word_before_hiding(env):
    bridge, runtime, _ = env
    runtime.hotkey_toggle()
    result = bridge.skip_current_and_escape(typo_count=2)
    assert result["cursor"] == 1
    assert bridge.next_word()["name"] == "word1"
    assert runtime.snapshot().phase == "HIDDEN"
    assert bridge.get_review()[0]["name"] == "word0"


def test_commit_word_during_soft_close_reaches_summary(env):
    bridge, runtime, _ = env
    from vibegap.daemon.events import Agent, AgentEvent, EventKind

    runtime.handle_event(AgentEvent(Agent.CODEX, "s", EventKind.RUNNING, ts=None))
    runtime.hotkey_toggle()  # 直接显示
    runtime.handle_event(AgentEvent(Agent.CODEX, "s", EventKind.DONE, ts=None))
    assert runtime.snapshot().phase == "SOFT_CLOSING"
    bridge.commit_word("pass")
    assert runtime.snapshot().phase == "SUMMARY"
