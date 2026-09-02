"""源码与 PyInstaller 冻结版共用的轻量命令分发。"""
from __future__ import annotations

import sys
from collections.abc import Callable

_MODES = {
    "--daemon": "daemon",
    "--ensure": "ensure",
    "--hotkey": "hotkey",
    "--install-agent": "install-agent",
    "--uninstall-agent": "uninstall-agent",
}


def split_mode(argv: list[str]) -> tuple[str, list[str]]:
    if argv and argv[0] in _MODES:
        return _MODES[argv[0]], argv[1:]
    return "daemon", argv


def _invoke(callback: Callable[[], None], argv: list[str]) -> None:
    previous = sys.argv
    try:
        sys.argv = [previous[0], *argv]
        callback()
    finally:
        sys.argv = previous


def main() -> None:
    mode, argv = split_mode(sys.argv[1:])
    if mode == "daemon":
        from vibegap.__main__ import main as daemon_main

        _invoke(daemon_main, argv)
    elif mode == "ensure":
        from vibegap.adapters.hook import ensure_main

        _invoke(ensure_main, argv)
    elif mode == "hotkey":
        from vibegap.adapters.windows_hotkey import main as hotkey_main

        _invoke(hotkey_main, argv)
    else:
        from vibegap.adapters.packaged import main as packaged_main

        packaged_main(mode, argv)
