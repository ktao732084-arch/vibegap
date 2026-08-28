"""全局热键:纯 ctypes RegisterHotKey + 独立消息循环线程。

注册失败(组合键被占)只记警告,不影响其他功能——手动唤醒仍可走 POST /toggle。
首次注册成功的组合持久化到 HOTKEY_PREF_PATH,之后每次启动优先注册它,
避免"上次是 G 这次变 W"的漂移(被占时才继续走候选链并更新记忆)。
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable

from vibegap.config import HOTKEY_PREF_PATH

logger = logging.getLogger(__name__)

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_HOTKEY_ID = 1

# 候选组合按序尝试(常用组合可能被其他程序占用),注册上哪个用哪个
_CANDIDATES: list[tuple[int, str]] = [
    (0x57, "Ctrl+Alt+W"),
    (0x47, "Ctrl+Alt+G"),
    (0x59, "Ctrl+Alt+Y"),
    (0x78, "Ctrl+Alt+F9"),
]

_active_label: str | None = None


def get_active_label() -> str | None:
    """实际注册成功的组合键;全部失败或未启动返回 None。"""
    return _active_label


def _ordered_candidates() -> list[tuple[int, str]]:
    """上次成功的组合排最前,其余保持原序。"""
    try:
        preferred = HOTKEY_PREF_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return list(_CANDIDATES)
    head = [item for item in _CANDIDATES if item[1] == preferred]
    tail = [item for item in _CANDIDATES if item[1] != preferred]
    return head + tail


def _remember(label: str) -> None:
    try:
        HOTKEY_PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
        HOTKEY_PREF_PATH.write_text(label, encoding="utf-8")
    except OSError as exc:
        logger.warning("hotkey preference not saved: %s", exc)


def start_hotkey_listener(callback: Callable[[], None]) -> None:
    """后台线程注册热键并泵消息;按下时调用 callback。"""

    def loop() -> None:
        global _active_label
        user32 = ctypes.windll.user32
        for vk, label in _ordered_candidates():
            if user32.RegisterHotKey(
                None, _HOTKEY_ID, _MOD_CONTROL | _MOD_ALT | _MOD_NOREPEAT, vk
            ):
                _active_label = label
                _remember(label)
                break
            logger.warning("hotkey %s taken, trying next", label)
        if _active_label is None:
            logger.warning("all hotkey candidates taken; manual wake via POST /toggle only")
            return
        logger.info("hotkey %s registered", _active_label)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                try:
                    callback()
                except Exception:  # noqa: BLE001 - 热键回调失败不能杀死消息循环
                    logger.exception("hotkey callback failed")

    threading.Thread(target=loop, name="vibegap-hotkey", daemon=True).start()
