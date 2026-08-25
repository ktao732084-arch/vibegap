"""JS↔Python 桥:UI 面板的唯一数据出口(词、进度、新闻、逃生)。

pywebview 的 js_api 调用来自其内部线程池,SQLite 连接以
check_same_thread=False + 显式锁串行化。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path

from wordgap.config import CONFIG_PATH, Settings
from wordgap.daemon.newsfeed import NewsFeed
from wordgap.daemon.runtime import Runtime
from wordgap.store import progress, stats, wordbooks
from wordgap.store.db import connect, kv_get, kv_set
from wordgap.store.wordbooks import WordbookError

_PREF_KEYS = ("auto_pronounce", "theme")  # UI 偏好白名单,kv 表以 pref_ 前缀存储
_THEMES = ("auto", "light", "dark")
# 设置面板可改的 config.json 项:key -> (最小值, 最大值)
_SETTING_LIMITS = {"popup_delay_sec": (5, 120), "daily_goal": (1, 1000)}

logger = logging.getLogger(__name__)


class Bridge:
    """暴露给前端的 API(方法名即 pywebview.api.<name>)。"""

    def __init__(
        self,
        db_path: Path | str,
        runtime: Runtime,
        newsfeed: NewsFeed,
        settings: Settings | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        self._runtime = runtime
        self._newsfeed = newsfeed
        self._settings = settings or Settings()
        self._config_path = config_path or CONFIG_PATH

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
        """状态栏用的进度概览(含每日目标)。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            if book_id is None:
                return {"error": "no_wordbook"}
            summary = progress.get_summary(self._conn, book_id)
            books = {b.id: b.name for b in wordbooks.list_wordbooks(self._conn)}
            today = stats.today_stats(self._conn)
        return {
            "cursor": summary.cursor,
            "total": summary.total,
            "mode": summary.mode,
            "book_name": books.get(book_id, "?"),
            "today": today.words_done,
            "goal": self._settings.daily_goal,
        }

    def peek_word(self, offset: int) -> dict:
        """按相对当前游标的偏移取词(←→浏览),只读不动游标。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            if book_id is None:
                return {"error": "no_wordbook"}
            summary = progress.get_summary(self._conn, book_id)
            position = summary.cursor + int(offset)
            if position < 0 or position >= summary.total:
                return {"error": "out_of_range"}
            nw = progress.get_word_at(self._conn, book_id, position)
        return {
            "name": nw.word.name,
            "trans": list(nw.word.trans),
            "usphone": nw.word.usphone,
            "position": nw.position,
            "total": nw.total,
            "offset": int(offset),
        }

    def list_books(self) -> list[dict]:
        """词书列表(切换菜单用)。"""
        with self._lock:
            current = wordbooks.get_current(self._conn)
            books = wordbooks.list_wordbooks(self._conn)
        return [
            {"id": b.id, "name": b.name, "count": b.word_count, "current": b.id == current}
            for b in books
        ]

    def set_book(self, book_id: int) -> dict:
        """切换当前词书。"""
        with self._lock:
            try:
                wordbooks.set_current(self._conn, int(book_id))
            except WordbookError as exc:
                return {"error": str(exc)}
        return {"ok": True}

    def get_review(self) -> list[dict]:
        """今日错词/跳过词队列(复习模式用)。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            if book_id is None:
                return []
            indices = stats.review_candidates(self._conn, book_id)
            words = wordbooks.get_words(self._conn, book_id)
        return [
            {
                "word_index": i,
                "name": words[i].name,
                "trans": list(words[i].trans),
                "usphone": words[i].usphone,
            }
            for i in indices
            if 0 <= i < len(words)
        ]

    def log_review(self, word_index: int, result: str, typo_count: int = 0) -> dict:
        """记录一次复习结果(不动进度游标)。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            if book_id is None:
                return {"error": "no_wordbook"}
            words = wordbooks.get_words(self._conn, book_id)
            idx = int(word_index)
            if not 0 <= idx < len(words):
                return {"error": "bad_index"}
            if result not in ("pass", "fail", "skip"):
                return {"error": "bad_result"}
            stats.log_review(
                self._conn, book_id, idx, words[idx].name, result, int(typo_count)
            )
        return {"ok": True}

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
        """会话状态:活跃/已完成计数 + 明细(会话面板用)。"""
        snap = self._runtime.snapshot()
        active = [s for s in snap.sessions if s.is_running]
        done = [s for s in snap.sessions if not s.is_running]
        to_dict = lambda s: {  # noqa: E731
            "agent": s.agent,
            "session_id": s.session_id,
            "running": s.is_running,
            "last_event_at": s.last_event_at,
            "cwd": s.cwd,
        }
        return {
            "phase": snap.phase,
            "any_running": snap.is_any_running,
            "running_agents": list(snap.running_agents),
            "active_count": len(active),
            "done_count": len(done),
            "sessions": [to_dict(s) for s in snap.sessions],
        }

    def request_focus(self) -> None:
        """点击弹窗时把系统键盘焦点抢过来(窗口默认不抢焦点,点击表示用户要输入)。"""
        import ctypes

        from wordgap.config import WINDOW_TITLE

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, WINDOW_TITLE)
            if hwnd:
                user32.SetForegroundWindow(hwnd)
        except Exception as exc:  # noqa: BLE001 - 焦点失败退化为"再点一次"
            logger.warning("request_focus failed: %s", exc)

    def activate_session(self, agent: str, cwd: str) -> dict:
        """把该会话所属的 agent 窗口置顶(按标题匹配项目名+agent 名);找不到退回开目录。"""
        import os

        from wordgap.ui import win32util

        leaf = Path(cwd).name if cwd else ""
        hints = {
            "claude-code": ["claude"],
            "codex": ["codex"],
            "pi": ["pi -", "pi agent"],
            "dsh": ["dsh", "deepseek"],
            "workbuddy": ["workbuddy"],
        }.get(str(agent), [])
        match = win32util.find_best_window([leaf], hints)
        if match is not None:
            hwnd, title = match
            logger.info("activate_session %s -> window '%s'", agent, title)
            if win32util.activate_window(hwnd):
                return {"ok": True, "via": "window", "title": title}
        target = Path(str(cwd)) if cwd else None
        if target and target.is_dir():
            os.startfile(str(target))  # noqa: S606
            return {"ok": True, "via": "folder"}
        return {"error": "not_found"}

    def open_path(self, path: str) -> dict:
        """打开某会话的项目目录(会话面板点击路径)。仅接受真实存在的目录。"""
        import os

        target = Path(str(path))
        if not target.is_dir():
            return {"error": "not_a_dir"}
        os.startfile(str(target))  # noqa: S606 - 本机目录浏览,来源为本地 agent hook
        return {"ok": True}

    def get_settings(self) -> dict:
        """设置面板数据:可调数值 + 当前词书模式。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            mode = None
            if book_id is not None:
                mode = progress.get_summary(self._conn, book_id).mode
        return {
            "popup_delay_sec": self._settings.popup_delay_sec,
            "daily_goal": self._settings.daily_goal,
            "mode": mode,
        }

    def set_setting(self, key: str, value: int) -> dict:
        """改数值设置:写 config.json 持久化 + runtime 热更新。"""
        if key not in _SETTING_LIMITS:
            return {"error": "bad_key"}
        low, high = _SETTING_LIMITS[key]
        try:
            value = max(low, min(high, int(value)))
        except (TypeError, ValueError):
            return {"error": "bad_value"}
        self._settings = replace(self._settings, **{key: value})
        self._runtime.update_settings(self._settings)
        self._persist_config(key, value)
        return {"ok": True, "value": value}

    def set_book_mode(self, mode: str) -> dict:
        """切换当前词书顺序/乱序(会重置该词书游标,前端已提示)。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            if book_id is None:
                return {"error": "no_wordbook"}
            try:
                progress.set_mode(self._conn, book_id, mode)
            except WordbookError as exc:
                return {"error": str(exc)}
        return {"ok": True}

    def _persist_config(self, key: str, value: int) -> None:
        try:
            raw = {}
            if self._config_path.exists():
                loaded = json.loads(self._config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw = loaded
            raw[key] = value
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("persist config failed: %s", exc)

    def get_prefs(self) -> dict:
        """UI 偏好(自动发音开关、主题)。"""
        with self._lock:
            sound = kv_get(self._conn, "pref_auto_pronounce")
            theme = kv_get(self._conn, "pref_theme")
        return {
            "auto_pronounce": sound != "0",
            "theme": theme if theme in _THEMES else "auto",
        }

    def set_pref(self, key: str, value) -> dict:
        """写 UI 偏好,持久化到 kv 表。"""
        if key not in _PREF_KEYS:
            return {"error": "bad_key"}
        if key == "theme":
            if value not in _THEMES:
                return {"error": "bad_value"}
            stored = str(value)
        else:
            stored = "1" if value else "0"
        with self._lock:
            kv_set(self._conn, f"pref_{key}", stored)
        return {"ok": True}

    def escape(self) -> None:
        """Esc 逃生:立即隐藏窗口。"""
        self._runtime.escape()

    def _close(self) -> None:
        """组合根关闭时调用(下划线前缀:不暴露给 JS)。"""
        with self._lock:
            self._conn.close()


def open_bridge(
    db_path: Path | str,
    runtime: Runtime,
    newsfeed: NewsFeed,
    settings: Settings | None = None,
) -> Bridge:
    """建 Bridge 前确保 schema 就绪(bridge 自身的连接不做建表)。"""
    connect(db_path).close()
    return Bridge(db_path, runtime, newsfeed, settings)
