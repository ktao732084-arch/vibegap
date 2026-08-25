"""Win32 窗口查找与激活(会话跳转用)。纯尽力而为:失败返回 None/False,不抛异常。"""
from __future__ import annotations

import ctypes
import logging

logger = logging.getLogger(__name__)

_SW_RESTORE = 9


def list_window_titles() -> list[tuple[int, str]]:
    """所有可见且有标题的顶层窗口 (hwnd, title)。"""
    user32 = ctypes.windll.user32
    result: list[tuple[int, str]] = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _collect(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                result.append((hwnd, buf.value))
        return True

    try:
        user32.EnumWindows(proc_type(_collect), 0)
    except Exception as exc:  # noqa: BLE001 - 枚举失败按"没找到"处理
        logger.warning("EnumWindows failed: %s", exc)
    return result


def find_best_window(
    strong_keywords: list[str],
    weak_keywords: list[str],
    exclude: tuple[str, ...] = ("wordgap",),
) -> int | None:
    """按关键词打分找最匹配窗口:强关键词 +2(项目名),弱关键词 +1(agent 名)。"""
    best_hwnd = None
    best_score = 0
    for hwnd, title in list_window_titles():
        lowered = title.lower()
        if any(word in lowered for word in exclude):
            continue
        score = sum(2 for kw in strong_keywords if kw and kw.lower() in lowered)
        score += sum(1 for kw in weak_keywords if kw and kw.lower() in lowered)
        if score > best_score:
            best_hwnd, best_score = hwnd, score
    return best_hwnd


def activate_window(hwnd: int) -> bool:
    """还原(若最小化)并置顶窗口。"""
    try:
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, _SW_RESTORE)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception as exc:  # noqa: BLE001
        logger.warning("activate_window failed: %s", exc)
        return False
