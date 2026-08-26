"""统计与配置加载单测。"""
import json
from datetime import date, datetime

import pytest

from vibegap.config import Settings, load_settings
from vibegap.store.db import connect
from vibegap.store.progress import commit_word
from vibegap.store.stats import (
    add_word_to_session,
    end_session,
    start_session,
    today_stats,
)
from vibegap.store.wordbooks import import_wordbook

NOW = datetime(2026, 8, 25, 10, 0, 0)


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def test_session_stat_lifecycle(conn):
    sid = start_session(conn, "claude-code", now=NOW)
    add_word_to_session(conn, sid)
    add_word_to_session(conn, sid)
    end_session(conn, sid, now=NOW)
    row = conn.execute("SELECT * FROM session_stat WHERE id = ?", (sid,)).fetchone()
    assert row["agent"] == "claude-code"
    assert row["words_done"] == 2
    assert row["ended_at"] == "2026-08-25T10:00:00"


def test_today_stats_counts_only_today(conn):
    book = import_wordbook(conn, "t", [{"name": "a", "trans": ["x"]}], mode="sequential")
    commit_word(conn, book.id, "pass", now=datetime(2026, 8, 24, 23, 0, 0))  # 昨天
    commit_word(conn, book.id, "fail", now=NOW)
    stats = today_stats(conn, today=date(2026, 8, 25))
    assert stats.words_done == 1
    assert stats.fail_count == 1


def test_today_stats_empty(conn):
    stats = today_stats(conn, today=date(2026, 8, 25))
    assert stats.words_done == 0
    assert stats.fail_count == 0


def test_load_settings_missing_file(tmp_path):
    assert load_settings(tmp_path / "none.json") == Settings()


def test_load_settings_overrides_valid_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"popup_delay_sec": 30}), encoding="utf-8")
    settings = load_settings(path)
    assert settings.popup_delay_sec == 30
    assert settings.summary_linger_sec == Settings().summary_linger_sec


def test_load_settings_rejects_invalid_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"popup_delay_sec": -5, "daemon_port": "abc", "session_ttl_min": True}),
        encoding="utf-8",
    )
    assert load_settings(path) == Settings()


def test_load_settings_bool_field(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"auto_popup": False}), encoding="utf-8")
    assert load_settings(path).auto_popup is False
    path.write_text(json.dumps({"auto_popup": 5}), encoding="utf-8")  # 非法类型
    assert load_settings(path).auto_popup is True


def test_load_settings_broken_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_load_settings_non_object_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1,2]", encoding="utf-8")
    assert load_settings(path) == Settings()
