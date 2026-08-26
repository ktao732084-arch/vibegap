"""学习统计:每轮弹窗记录与日汇总。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class TodayStats:
    words_done: int
    fail_count: int


def start_session(
    conn: sqlite3.Connection, agent: str, now: datetime | None = None
) -> int:
    """记录一轮弹窗开始,返回 session_stat id。"""
    ts = (now or datetime.now()).isoformat(timespec="seconds")
    with conn:
        cur = conn.execute(
            "INSERT INTO session_stat (agent, started_at) VALUES (?, ?)", (agent, ts)
        )
    return cur.lastrowid


def end_session(
    conn: sqlite3.Connection, session_id: int, now: datetime | None = None
) -> None:
    """记录一轮弹窗结束。"""
    ts = (now or datetime.now()).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            "UPDATE session_stat SET ended_at = ? WHERE id = ?", (ts, session_id)
        )


def add_word_to_session(conn: sqlite3.Connection, session_id: int) -> None:
    """本轮弹窗背词数 +1。"""
    with conn:
        conn.execute(
            "UPDATE session_stat SET words_done = words_done + 1 WHERE id = ?",
            (session_id,),
        )


def review_candidates(
    conn: sqlite3.Connection, wordbook_id: int, today: date | None = None
) -> list[int]:
    """今日"最后一次结果不是 pass"的词(word_index 列表),供错词复习。"""
    prefix = (today or date.today()).isoformat()
    rows = conn.execute(
        "SELECT word_index, result FROM word_log "
        "WHERE wordbook_id = ? AND seen_at LIKE ? || '%' ORDER BY id",
        (wordbook_id, prefix),
    ).fetchall()
    latest: dict[int, str] = {}
    for row in rows:
        latest[row["word_index"]] = row["result"]
    return [idx for idx, result in latest.items() if result != "pass"]


def log_review(
    conn: sqlite3.Connection,
    wordbook_id: int,
    word_index: int,
    word: str,
    result: str,
    typo_count: int = 0,
    now: datetime | None = None,
) -> None:
    """复习记录写 word_log(不动进度游标)。"""
    ts = (now or datetime.now()).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            "INSERT INTO word_log (wordbook_id, word_index, word, result, typo_count, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (wordbook_id, word_index, word, result, typo_count, ts),
        )


def today_stats(conn: sqlite3.Connection, today: date | None = None) -> TodayStats:
    """今日背词总数与不会拼的个数(按 word_log.seen_at 日期前缀)。"""
    prefix = (today or date.today()).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN result = 'fail' THEN 1 ELSE 0 END) AS fails "
        "FROM word_log WHERE seen_at LIKE ? || '%'",
        (prefix,),
    ).fetchone()
    return TodayStats(words_done=row["total"], fail_count=row["fails"] or 0)
