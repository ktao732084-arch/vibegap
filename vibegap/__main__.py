"""程序入口(组合根):python -m vibegap 启动 daemon + 悬浮窗。

pywebview 要求主循环占主线程;uvicorn 与 ticker 各占一个 daemon 线程。
"""
from __future__ import annotations

import logging
import logging.handlers
import threading
import time

import uvicorn

from vibegap.config import (
    CODEX_SESSIONS_DIR,
    DAEMON_HOST,
    DB_PATH,
    DICTS_DIR,
    LOG_DIR,
    LOG_RETENTION_DAYS,
    TICK_INTERVAL_SEC,
    Settings,
    load_settings,
)
from vibegap.daemon.app import create_app
from vibegap.daemon.codex_watcher import CodexWatcher
from vibegap.daemon.events import Agent, AgentEvent, EventKind
from vibegap.daemon.newsfeed import NewsFeed
from vibegap.daemon.runtime import Runtime
from vibegap.store import db as store_db
from vibegap.store import wordbooks
from vibegap.ui.bridge import open_bridge
from vibegap.ui.hotkey import start_hotkey_listener
from vibegap.ui.toast import ToastNotifier
from vibegap.ui.window import WindowNotifier, create_window

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "daemon.log",
        when="midnight",
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler, logging.StreamHandler()],
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _bootstrap_db() -> None:
    """首次运行:导入内置词书并设为当前。"""
    conn = store_db.connect(DB_PATH)
    try:
        if wordbooks.list_wordbooks(conn):
            return
        for path in sorted(DICTS_DIR.glob("*.json")):
            try:
                book = wordbooks.import_wordbook_file(conn, path)
                logger.info("imported wordbook %s (%d words)", book.name, book.word_count)
            except wordbooks.WordbookError as exc:
                logger.error("skip dict %s: %s", path.name, exc)
        books = wordbooks.list_wordbooks(conn)
        if books:
            wordbooks.set_current(conn, books[0].id)
    finally:
        conn.close()


def _kv_get(key: str) -> str | None:
    conn = store_db.connect(DB_PATH)
    try:
        return store_db.kv_get(conn, key)
    finally:
        conn.close()


def _kv_set(key: str, value: str) -> None:
    conn = store_db.connect(DB_PATH)
    try:
        store_db.kv_set(conn, key, value)
    finally:
        conn.close()


def _start_server(runtime: Runtime, settings: Settings) -> None:
    app = create_app(runtime)
    config = uvicorn.Config(app, host=DAEMON_HOST, port=settings.daemon_port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="vibegap-server", daemon=True).start()


def _make_codex_watcher(runtime: Runtime) -> CodexWatcher | None:
    """codex 适配走日志监听(其 notify 已被 Codex Desktop 占用,不碰)。"""
    if not CODEX_SESSIONS_DIR.is_dir():
        logger.info("codex not detected, watcher disabled")
        return None

    def emit(sid: str, kind: str, cwd: str) -> None:
        runtime.handle_event(
            AgentEvent(
                agent=Agent.CODEX,
                session_id=sid,
                kind=EventKind.RUNNING if kind == "running" else EventKind.DONE,
                ts=None,
                cwd=cwd,
            )
        )

    logger.info("codex watcher enabled: %s", CODEX_SESSIONS_DIR)
    return CodexWatcher(CODEX_SESSIONS_DIR, emit)


def _start_ticker(
    runtime: Runtime, newsfeed: NewsFeed, watcher: CodexWatcher | None
) -> None:
    def loop() -> None:
        while True:
            time.sleep(TICK_INTERVAL_SEC)
            try:
                runtime.tick()
                newsfeed.maybe_refresh()
                if watcher is not None:
                    watcher.poll()
            except Exception:  # noqa: BLE001 - ticker 线程绝不能死
                logger.exception("ticker iteration failed")

    threading.Thread(target=loop, name="vibegap-ticker", daemon=True).start()


def main() -> None:
    """启动入口。"""
    import webview

    _setup_logging()
    settings = load_settings()
    _bootstrap_db()

    notifier = WindowNotifier(fallback=ToastNotifier())
    runtime = Runtime(settings=settings, notifier=notifier)
    newsfeed = NewsFeed()
    newsfeed.maybe_refresh()
    bridge = open_bridge(DB_PATH, runtime, newsfeed, settings)

    _start_server(runtime, settings)
    _start_ticker(runtime, newsfeed, _make_codex_watcher(runtime))
    start_hotkey_listener(runtime.hotkey_toggle)

    window = create_window(bridge, _kv_get, _kv_set)
    notifier.set_window(window)
    logger.info("vibegap started (port %d)", settings.daemon_port)
    webview.start()
    bridge._close()


if __name__ == "__main__":
    main()
