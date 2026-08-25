"""进度游标:取下一个词、提交结果。断点续背的唯一真相(spec §3.1)。"""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from wordgap.config import (
    MODE_SEQUENTIAL,
    MODE_SHUFFLED,
    SEED_RANGE,
    VALID_MODES,
    VALID_RESULTS,
)
from wordgap.store.wordbooks import Word, WordbookError, get_words


@dataclass(frozen=True)
class NextWord:
    word: Word
    original_index: int   # 洗牌前的原始下标(word_log 用)
    position: int         # 当前游标(0-based)
    total: int


@dataclass(frozen=True)
class ProgressSummary:
    wordbook_id: int
    mode: str
    cursor: int
    total: int
    is_round_completed: bool  # 本次提交是否恰好背完一整轮


def seeded_order(count: int, seed: int) -> list[int]:
    """固定种子洗牌:seed 不变则顺序确定,断点可续。"""
    order = list(range(count))
    random.Random(seed).shuffle(order)
    return order


def get_next_word(conn: sqlite3.Connection, wordbook_id: int) -> NextWord:
    """按当前游标取下一个词。"""
    row = _get_progress_row(conn, wordbook_id)
    words = get_words(conn, wordbook_id)
    index = _word_index_at(row, len(words), row["cursor"])
    return NextWord(
        word=words[index],
        original_index=index,
        position=row["cursor"],
        total=len(words),
    )


def commit_word(
    conn: sqlite3.Connection,
    wordbook_id: int,
    result: str,
    typo_count: int = 0,
    now: datetime | None = None,
    next_seed: int | None = None,
) -> ProgressSummary:
    """提交当前词的结果:写 word_log 并推进游标。每词一提交,立即落库(§3.1)。

    背完一轮时游标归零并换新 seed(next_seed 供测试注入)。
    """
    if result not in VALID_RESULTS:
        raise WordbookError(f"invalid result: {result}")
    row = _get_progress_row(conn, wordbook_id)
    words = get_words(conn, wordbook_id)
    total = len(words)
    index = _word_index_at(row, total, row["cursor"])
    ts = (now or datetime.now()).isoformat(timespec="seconds")

    new_cursor = row["cursor"] + 1
    is_round_completed = new_cursor >= total
    new_seed = row["shuffle_seed"]
    if is_round_completed:
        new_cursor = 0
        if row["mode"] == MODE_SHUFFLED:
            new_seed = next_seed if next_seed is not None else random.randrange(SEED_RANGE)

    with conn:
        conn.execute(
            "INSERT INTO word_log (wordbook_id, word_index, word, result, typo_count, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (wordbook_id, index, words[index].name, result, typo_count, ts),
        )
        conn.execute(
            "UPDATE progress SET cursor = ?, shuffle_seed = ?, updated_at = ? "
            "WHERE wordbook_id = ?",
            (new_cursor, new_seed, ts, wordbook_id),
        )
    return ProgressSummary(
        wordbook_id=wordbook_id,
        mode=row["mode"],
        cursor=new_cursor,
        total=total,
        is_round_completed=is_round_completed,
    )


def get_summary(conn: sqlite3.Connection, wordbook_id: int) -> ProgressSummary:
    """当前进度概览(状态栏 355/3674 用)。"""
    row = _get_progress_row(conn, wordbook_id)
    total_row = conn.execute(
        "SELECT word_count FROM wordbook WHERE id = ?", (wordbook_id,)
    ).fetchone()
    return ProgressSummary(
        wordbook_id=wordbook_id,
        mode=row["mode"],
        cursor=row["cursor"],
        total=total_row["word_count"],
        is_round_completed=False,
    )


def set_mode(
    conn: sqlite3.Connection,
    wordbook_id: int,
    mode: str,
    seed: int | None = None,
    now: datetime | None = None,
) -> None:
    """切换顺序/乱序。切换会重置游标并换 seed(顺序语义已变,旧游标无意义)。"""
    if mode not in VALID_MODES:
        raise WordbookError(f"unknown mode: {mode}")
    _get_progress_row(conn, wordbook_id)
    new_seed = None
    if mode == MODE_SHUFFLED:
        new_seed = seed if seed is not None else random.randrange(SEED_RANGE)
    ts = (now or datetime.now()).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            "UPDATE progress SET mode = ?, shuffle_seed = ?, cursor = 0, updated_at = ? "
            "WHERE wordbook_id = ?",
            (mode, new_seed, ts, wordbook_id),
        )


def _get_progress_row(conn: sqlite3.Connection, wordbook_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT wordbook_id, mode, shuffle_seed, cursor FROM progress WHERE wordbook_id = ?",
        (wordbook_id,),
    ).fetchone()
    if row is None:
        raise WordbookError(f"no progress for wordbook {wordbook_id}")
    return row


def _word_index_at(row: sqlite3.Row, total: int, cursor: int) -> int:
    if cursor >= total:
        raise WordbookError(f"cursor {cursor} out of range (total {total})")
    if row["mode"] == MODE_SEQUENTIAL:
        return cursor
    return seeded_order(total, row["shuffle_seed"])[cursor]
