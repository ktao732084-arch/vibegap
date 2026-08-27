"""程序入口(组合根):python -m vibegap 启动 daemon + 悬浮窗。

pywebview 要求主循环占主线程;uvicorn 与 ticker 各占一个 daemon 线程。
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import socket
import threading
import time
from dataclasses import replace

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
from vibegap.daemon.app import PanelApi, create_app
from vibegap.daemon.codex_watcher import CodexWatcher
from vibegap.daemon.events import Agent, AgentEvent, EventKind
from vibegap.daemon.newsfeed import NewsFeed
from vibegap.daemon.runtime import Runtime
from vibegap.adapters.windows_hotkey import is_installed as shell_hotkey_installed
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


def _bind_server_socket(settings: Settings) -> socket.socket:
    """在主线程预绑定端口;失败时必须在创建窗口前退出。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((DAEMON_HOST, settings.daemon_port))
        return sock
    except Exception:
        sock.close()
        raise


def _start_server(
    runtime: Runtime,
    settings: Settings,
    panel: PanelApi,
    sock: socket.socket,
) -> tuple[uvicorn.Server, threading.Thread]:
    app = create_app(runtime, panel)
    config = uvicorn.Config(app, host=DAEMON_HOST, port=settings.daemon_port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        name="vibegap-server",
        daemon=True,
    )
    thread.start()
    return server, thread


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
    runtime: Runtime,
    newsfeed: NewsFeed,
    watcher: CodexWatcher | None,
    request_exit,
) -> None:
    def loop() -> None:
        while True:
            time.sleep(TICK_INTERVAL_SEC)
            try:
                runtime.tick()
                newsfeed.maybe_refresh()
                if watcher is not None:
                    watcher.poll()
                if runtime.should_exit_idle():
                    logger.info("idle timeout reached; exiting")
                    request_exit()
                    return
            except Exception:  # noqa: BLE001 - ticker 线程绝不能死
                logger.exception("ticker iteration failed")

    threading.Thread(target=loop, name="vibegap-ticker", daemon=True).start()


def main() -> None:
    """启动入口。"""
    _setup_logging()
    parser = argparse.ArgumentParser(description="VibeGap desktop runtime")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    settings = load_settings()
    if args.port is not None:
        settings = replace(settings, daemon_port=args.port)
    try:
        server_socket = _bind_server_socket(settings)
    except OSError as exc:
        logger.info(
            "vibegap already running or port %d unavailable: %s",
            settings.daemon_port,
            exc,
        )
        return

    import webview

    _bootstrap_db()

    notifier = WindowNotifier(fallback=ToastNotifier())
    runtime = Runtime(settings=settings, notifier=notifier)
    newsfeed = NewsFeed()
    newsfeed.maybe_refresh()
    bridge = open_bridge(DB_PATH, runtime, newsfeed, settings)

    server, server_thread = _start_server(runtime, settings, bridge, server_socket)
    window = create_window(bridge, _kv_get, _kv_set)
    notifier.set_window(window)

    def request_exit() -> None:
        try:
            window.destroy()
        except Exception:  # noqa: BLE001 - 退出竞态时 webview 可能已经销毁
            logger.exception("idle window destroy failed")

    _start_ticker(runtime, newsfeed, _make_codex_watcher(runtime), request_exit)
    if shell_hotkey_installed():
        logger.info("shell hotkey installed; in-process hotkey listener disabled")
    else:
        start_hotkey_listener(runtime.hotkey_toggle)

    logger.info("vibegap started (port %d)", settings.daemon_port)
    try:
        webview.start()
    finally:
        server.should_exit = True
        server_thread.join(timeout=2)
        server_socket.close()
        bridge._close()


if __name__ == "__main__":
    main()
