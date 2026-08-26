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

from vibegap.config import (
    CLAUDE_SETTINGS_PATH,
    CODEX_SESSIONS_DIR,
    CONFIG_PATH,
    DSH_DIR,
    PI_DIR,
    WORKBUDDY_SETTINGS_PATH,
    Settings,
)
from vibegap.daemon.newsfeed import NewsFeed
from vibegap.daemon.runtime import Runtime
from vibegap.store import progress, stats, wordbooks
from vibegap.store.db import connect, kv_get, kv_set
from vibegap.store.wordbooks import WordbookError

_PREF_KEYS = ("auto_pronounce", "theme")  # UI 偏好白名单,kv 表以 pref_ 前缀存储
_THEMES = ("auto", "light", "dark")
# 设置面板可改的 config.json 项:key -> (最小值, 最大值)
_SETTING_LIMITS = {"popup_delay_sec": (5, 120), "daily_goal": (1, 1000)}

# 各 agent 的"恢复会话"命令模板(官方 CLI 机制)
_RESUME_COMMANDS = {
    "claude-code": "claude --resume {sid}",
    "codex": "codex resume {sid}",
}

# 走 Claude-Code 兼容钩子安装器接入的 agent -> settings.json 路径
_HOOK_TARGETS = {
    "claude-code": CLAUDE_SETTINGS_PATH,
    "workbuddy": WORKBUDDY_SETTINGS_PATH,
}
_INSTALLER = Path(__file__).resolve().parents[1] / "adapters" / "claude_code" / "install.py"

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

        from vibegap.config import WINDOW_TITLE

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, WINDOW_TITLE)
            if hwnd:
                user32.SetForegroundWindow(hwnd)
        except Exception as exc:  # noqa: BLE001 - 焦点失败退化为"再点一次"
            logger.warning("request_focus failed: %s", exc)

    def resume_session(self, agent: str, session_id: str, cwd: str = "") -> dict:
        """在新终端里用官方 CLI 恢复该对话(claude --resume / codex resume)。"""
        import re
        import subprocess

        if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", str(session_id or "")):
            return {"error": "bad_session_id"}
        template = _RESUME_COMMANDS.get(str(agent))
        if template is None:
            return {"error": "unsupported_agent"}
        workdir = str(cwd) if cwd and Path(str(cwd)).is_dir() else None
        try:
            subprocess.Popen(  # noqa: S603 - 命令模板固定,sid 已白名单校验
                ["cmd.exe", "/k", template.format(sid=session_id)],
                cwd=workdir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError as exc:
            logger.error("resume_session failed: %s", exc)
            return {"error": "launch_failed"}
        return {"ok": True}

    def get_agents(self) -> list[dict]:
        """设置面板 Agent 区块:每个 agent 的检测/接入状态。"""
        return [
            _hook_agent_status("claude-code", CLAUDE_SETTINGS_PATH),
            {
                "agent": "codex",
                "status": "connected" if CODEX_SESSIONS_DIR.is_dir() else "missing",
                "detail": "自动 · 日志监听" if CODEX_SESSIONS_DIR.is_dir() else "未检测到",
            },
            _hook_agent_status("workbuddy", WORKBUDDY_SETTINGS_PATH),
            {
                "agent": "pi",
                "status": "manual" if PI_DIR.is_dir() else "missing",
                "detail": "手动装扩展(adapters/pi)" if PI_DIR.is_dir() else "未检测到",
            },
            {
                "agent": "dsh",
                "status": "manual" if DSH_DIR.is_dir() else "missing",
                "detail": "hook bridge(见 adapters/dsh)" if DSH_DIR.is_dir() else "未检测到",
            },
        ]

    def install_agent(self, agent: str) -> dict:
        """一键接入(复用 claude_code 安装器,merge+备份)。"""
        return self._run_installer(agent, uninstall=False)

    def uninstall_agent(self, agent: str) -> dict:
        """一键移除本工具写入的钩子。"""
        return self._run_installer(agent, uninstall=True)

    def _run_installer(self, agent: str, uninstall: bool) -> dict:
        import subprocess
        import sys

        target = _HOOK_TARGETS.get(str(agent))
        if target is None:
            return {"error": "unsupported_agent"}
        if not target.parent.is_dir():
            return {"error": "not_detected"}
        cmd = [
            sys.executable, str(_INSTALLER),
            "--settings", str(target),
            "--agent", str(agent),
            "--port", str(self._settings.daemon_port),
        ]
        if uninstall:
            cmd.append("--uninstall")
        try:
            proc = subprocess.run(  # noqa: S603 - 固定安装器路径+白名单参数
                cmd, capture_output=True, text=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.error("installer failed: %s", exc)
            return {"error": "installer_failed"}
        if proc.returncode != 0:
            logger.error("installer exit %d: %s", proc.returncode, proc.stderr[-300:])
            return {"error": "installer_failed"}
        return {"ok": True}

    def get_settings(self) -> dict:
        """设置面板数据:可调数值 + 当前词书模式。"""
        with self._lock:
            book_id = wordbooks.get_current(self._conn)
            mode = None
            if book_id is not None:
                mode = progress.get_summary(self._conn, book_id).mode
        from vibegap.ui import hotkey

        return {
            "popup_delay_sec": self._settings.popup_delay_sec,
            "daily_goal": self._settings.daily_goal,
            "auto_popup": self._settings.auto_popup,
            "hotkey": hotkey.get_active_label() or "",
            "mode": mode,
        }

    def set_setting(self, key: str, value) -> dict:
        """改设置:写 config.json 持久化 + runtime 热更新。"""
        if key == "auto_popup":
            flag = bool(value)
            self._settings = replace(self._settings, auto_popup=flag)
            self._runtime.update_settings(self._settings)
            self._persist_config(key, flag)
            return {"ok": True, "value": flag}
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


def _hook_agent_status(name: str, settings_path: Path) -> dict:
    """走 Claude 兼容钩子的 agent:按配置目录与 vibegap 标记判定状态。"""
    if not settings_path.parent.is_dir():
        return {"agent": name, "status": "missing", "detail": "未检测到"}
    try:
        content = settings_path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        content = ""
    if "vibegap" in content:
        return {"agent": name, "status": "connected", "detail": "已接入"}
    return {"agent": name, "status": "available", "detail": "可接入"}


def open_bridge(
    db_path: Path | str,
    runtime: Runtime,
    newsfeed: NewsFeed,
    settings: Settings | None = None,
) -> Bridge:
    """建 Bridge 前确保 schema 就绪(bridge 自身的连接不做建表)。"""
    connect(db_path).close()
    return Bridge(db_path, runtime, newsfeed, settings)
