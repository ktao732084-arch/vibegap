"""进度游标单测:断点续背是这里验证的核心。"""
from datetime import datetime

import pytest

from vibegap.store.db import connect
from vibegap.store.progress import (
    commit_word,
    get_next_word,
    get_summary,
    seeded_order,
    set_mode,
)
from vibegap.store.wordbooks import WordbookError, import_wordbook

WORDS = [{"name": f"word{i:02d}", "trans": [f"释义{i}"]} for i in range(10)]
NOW = datetime(2026, 8, 25, 10, 0, 0)


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def _book(conn, mode="sequential", seed=42):
    return import_wordbook(conn, "test", WORDS, mode=mode, seed=seed)


def test_sequential_order(conn):
    book = _book(conn, "sequential")
    seen = []
    for _ in range(10):
        nw = get_next_word(conn, book.id)
        seen.append(nw.word.name)
        commit_word(conn, book.id, "pass", now=NOW)
    assert seen == [f"word{i:02d}" for i in range(10)]


def test_shuffled_covers_all_words_once_per_round(conn):
    book = _book(conn, "shuffled", seed=42)
    seen = []
    for _ in range(10):
        seen.append(get_next_word(conn, book.id).word.name)
        commit_word(conn, book.id, "pass", now=NOW, next_seed=7)
    assert sorted(seen) == [f"word{i:02d}" for i in range(10)]
    assert seen != sorted(seen)  # seed=42 对 10 词确实打乱了顺序


def test_seeded_order_is_stable():
    assert seeded_order(100, 42) == seeded_order(100, 42)
    assert seeded_order(100, 42) != seeded_order(100, 43)


def test_resume_after_reopen(conn, tmp_path):
    # 断点续背的端到端验证:关库重开(模拟换对话/重启),游标不丢
    db_path = tmp_path / "t.db"
    c1 = connect(db_path)
    book = import_wordbook(c1, "test", WORDS, mode="shuffled", seed=42)
    first_three = []
    for _ in range(3):
        first_three.append(get_next_word(c1, book.id).word.name)
        commit_word(c1, book.id, "pass", now=NOW)
    c1.close()

    c2 = connect(db_path)
    expected_order = [WORDS[i]["name"] for i in seeded_order(10, 42)]
    assert first_three == expected_order[:3]
    assert get_next_word(c2, book.id).word.name == expected_order[3]
    assert get_summary(c2, book.id).cursor == 3
    c2.close()


def test_round_completion_resets_cursor_and_reseeds(conn):
    book = _book(conn, "shuffled", seed=42)
    for i in range(10):
        summary = commit_word(conn, book.id, "pass", now=NOW, next_seed=7)
        assert summary.is_round_completed == (i == 9)
    assert summary.cursor == 0
    row = conn.execute(
        "SELECT shuffle_seed FROM progress WHERE wordbook_id = ?", (book.id,)
    ).fetchone()
    assert row["shuffle_seed"] == 7  # 新一轮换了 seed,顺序不同于上一轮


def test_sequential_round_completion_keeps_no_seed(conn):
    book = _book(conn, "sequential")
    for _ in range(10):
        summary = commit_word(conn, book.id, "pass", now=NOW)
    assert summary.is_round_completed
    assert get_next_word(conn, book.id).word.name == "word00"


def test_commit_writes_word_log(conn):
    book = _book(conn, "sequential")
    commit_word(conn, book.id, "fail", typo_count=2, now=NOW)
    row = conn.execute("SELECT * FROM word_log").fetchone()
    assert row["word"] == "word00"
    assert row["result"] == "fail"
    assert row["typo_count"] == 2
    assert row["seen_at"] == "2026-08-25T10:00:00"


def test_skip_advances_cursor(conn):
    book = _book(conn, "sequential")
    commit_word(conn, book.id, "skip", now=NOW)
    assert get_next_word(conn, book.id).word.name == "word01"


def test_invalid_result_rejected(conn):
    book = _book(conn, "sequential")
    with pytest.raises(WordbookError):
        commit_word(conn, book.id, "maybe")


def test_set_mode_preserves_cursor(conn):
    book = _book(conn, "sequential")
    commit_word(conn, book.id, "pass", now=NOW)
    commit_word(conn, book.id, "pass", now=NOW)
    set_mode(conn, book.id, "shuffled", seed=99, now=NOW)
    summary = get_summary(conn, book.id)
    assert summary.cursor == 2  # 已背数量保留
    assert summary.mode == "shuffled"
    set_mode(conn, book.id, "sequential", now=NOW)
    assert get_summary(conn, book.id).cursor == 2


def test_progress_missing_rejected(conn):
    with pytest.raises(WordbookError):
        get_next_word(conn, 999)


def test_set_mode_invalid_rejected(conn):
    book = _book(conn, "sequential")
    with pytest.raises(WordbookError):
        set_mode(conn, book.id, "bogus")


def test_corrupted_cursor_out_of_range_rejected(conn):
    book = _book(conn, "sequential")
    with conn:
        conn.execute(
            "UPDATE progress SET cursor = 99 WHERE wordbook_id = ?", (book.id,)
        )
    with pytest.raises(WordbookError):
        get_next_word(conn, book.id)
