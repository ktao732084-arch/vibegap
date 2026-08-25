"""JS↔Python 桥:UI 面板的唯一数据出口(词、进度、新闻、逃生)。

pywebview 的 js_api 调用来自其内部线程池,SQLite 连接以
check_same_thread=False + 显式锁串行化。
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from wordgap.daemon.newsfeed import NewsFeed
from wordgap.daemon.runtime import Runtime
from wordgap.store import progress, wordbooks
from wordgap.store.db import connect
from wordgap.store.wordbooks import WordbookError

logger = logging.getLogger(__name__)


class Bridge:
    """暴露给前端的 API(方法名即 pywebview.api.<name>)。"""

    def __init__(self, db_path: Path | str, runtime: Runtime, newsfeed: NewsFeed) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        self._runtime = runtime
        self._newsfeed = newsfeed

    def next_word(self) -> dict:
        """当前词书的下一个词 + 进度;无词书时返回 error 字段。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            if book_id is None:
                return {"error": "no_wordbook"}
            try:
                nw = progress.get_next_word(self._conn, book_id)
            except WordbookError as exc:
                logger.error("next_word failed: %s", exc)
                return {"error": str(exc)}
            return {
                "name": nw.word.name,
                "trans": list(nw.word.trans),
                "usphone": nw.word.usphone,
                "position": nw.position,
                "total": nw.total,
            }

    def commit_word(self, result: str, typo_count: int = 0) -> dict:
        """提交当前词;推进游标并驱动调度器(软关闭在此转小结)。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            if book_id is None:
                return {"error": "no_wordbook"}
            try:
                summary = progress.commit_word(
                    self._conn, book_id, result, typo_count=int(typo_count)
                )
            except WordbookError as exc:
                logger.error("commit_word failed: %s", exc)
                return {"error": str(exc)}
        self._runtime.word_committed()
        return {
            "cursor": summary.cursor,
            "total": summary.total,
            "round_completed": summary.is_round_completed,
        }

    def get_progress(self) -> dict:
        """状态栏用的进度概览。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            if book_id is None:
                return {"error": "no_wordbook"}
            summary = progress.get_summary(self._conn, book_id)
            books = {b.id: b.name for b in wordbooks.list_wordbooks(self._conn)}
        return {
            "cursor": summary.cursor,
            "total": summary.total,
            "mode": summary.mode,
            "book_name": books.get(book_id, "?"),
        }

    def get_news(self) -> list[dict]:
        """新闻轮播条数据;空列表 = 隐藏轮播条。"""
        return [
            {
                "title": n.title,
                "source": n.source,
                "url": n.url,
                "published_at": n.published_at,
            }
            for n in self._newsfeed.items()
        ]

    def get_state(self) -> dict:
        """会话状态展示:哪些 agent 在跑(状态栏小圆点)。"""
        snap = self._runtime.snapshot()
        return {
            "phase": snap.phase,
            "any_running": snap.is_any_running,
            "running_agents": list(snap.running_agents),
        }

    def escape(self) -> None:
        """Esc 逃生:立即隐藏窗口。"""
        self._runtime.escape()

    def _close(self) -> None:
        """组合根关闭时调用(下划线前缀:不暴露给 JS)。"""
        with self._lock:
            self._conn.close()


def open_bridge(db_path: Path | str, runtime: Runtime, newsfeed: NewsFeed) -> Bridge:
    """建 Bridge 前确保 schema 就绪(bridge 自身的连接不做建表)。"""
    connect(db_path).close()
    return Bridge(db_path, runtime, newsfeed)
