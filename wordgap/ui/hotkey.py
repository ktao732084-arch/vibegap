"""全局热键(Ctrl+Alt+W):纯 ctypes RegisterHotKey + 独立消息循环线程。

注册失败(组合键被占)只记警告,不影响其他功能——手动唤醒仍可走 POST /toggle。
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable

logger = logging.getLogger(__name__)

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_VK_W = 0x57
_HOTKEY_ID = 1

HOTKEY_LABEL = "Ctrl+Alt+W"


def start_hotkey_listener(callback: Callable[[], None]) -> None:
    """后台线程注册热键并泵消息;按下时调用 callback。"""

    def loop() -> None:
        user32 = ctypes.windll.user32
        registered = user32.RegisterHotKey(
            None, _HOTKEY_ID, _MOD_CONTROL | _MOD_ALT | _MOD_NOREPEAT, _VK_W
        )
        if not registered:
            logger.warning("hotkey %s registration failed (already taken?)", HOTKEY_LABEL)
            return
        logger.info("hotkey %s registered", HOTKEY_LABEL)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                try:
                    callback()
                except Exception:  # noqa: BLE001 - 热键回调失败不能杀死消息循环
                    logger.exception("hotkey callback failed")

    threading.Thread(target=loop, name="wordgap-hotkey", daemon=True).start()
