"""程序入口(组合根):python -m wordgap 启动 daemon + tick 线程。"""
from __future__ import annotations

import logging
import logging.handlers
import threading
import time

import uvicorn

from wordgap.config import (
    DAEMON_HOST,
    LOG_DIR,
    LOG_RETENTION_DAYS,
    TICK_INTERVAL_SEC,
    load_settings,
)
from wordgap.daemon.app import create_app
from wordgap.daemon.runtime import Runtime
from wordgap.ui.toast import ToastNotifier


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


def _start_ticker(runtime: Runtime) -> threading.Thread:
    def loop() -> None:
        while True:
            time.sleep(TICK_INTERVAL_SEC)
            runtime.tick()

    thread = threading.Thread(target=loop, name="wordgap-ticker", daemon=True)
    thread.start()
    return thread


def main() -> None:
    """启动入口。"""
    _setup_logging()
    settings = load_settings()
    runtime = Runtime(settings=settings, notifier=ToastNotifier())
    _start_ticker(runtime)
    app = create_app(runtime)
    uvicorn.run(app, host=DAEMON_HOST, port=settings.daemon_port, log_level="warning")


if __name__ == "__main__":
    main()
