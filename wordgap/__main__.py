"""程序入口(组合根):python -m wordgap 启动 daemon + 悬浮窗。

pywebview 要求主循环占主线程;uvicorn 与 ticker 各占一个 daemon 线程。
"""
from __future__ import annotations

import logging
import logging.handlers
import threading
import time

import uvicorn

from wordgap.config import (
    DAEMON_HOST,
    DB_PATH,
    DICTS_DIR,
    LOG_DIR,
    LOG_RETENTION_DAYS,
    TICK_INTERVAL_SEC,
    Settings,
    load_settings,
)
from wordgap.daemon.app import create_app
from wordgap.daemon.newsfeed import NewsFeed
from wordgap.daemon.runtime import Runtime
from wordgap.store import db as store_db
from wordgap.store import wordbooks
from wordgap.ui.bridge import open_bridge
from wordgap.ui.toast import ToastNotifier
from wordgap.ui.window import WindowNotifier, create_window

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
    threading.Thread(target=server.run, name="wordgap-server", daemon=True).start()


def _start_ticker(runtime: Runtime, newsfeed: NewsFeed) -> None:
    def loop() -> None:
        while True:
            time.sleep(TICK_INTERVAL_SEC)
            runtime.tick()
            newsfeed.maybe_refresh()

    threading.Thread(target=loop, name="wordgap-ticker", daemon=True).start()


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
    _start_ticker(runtime, newsfeed)

    window = create_window(bridge, _kv_get, _kv_set)
    notifier.set_window(window)
    logger.info("wordgap started (port %d)", settings.daemon_port)
    webview.start()
    bridge._close()


if __name__ == "__main__":
    main()
