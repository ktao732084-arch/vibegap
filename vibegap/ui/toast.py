"""M1 占位通知器:Windows toast(PowerShell WinRT),失败降级为日志。

M2 将被 pywebview 悬浮窗替换,但 toast 保留作为 UI 不可用时的兜底。
标题/正文经环境变量传给 PowerShell,避免引号与编码问题。
"""
from __future__ import annotations

import logging
import os
import subprocess

from vibegap.config import TOAST_TIMEOUT_SEC
from vibegap.daemon.events import AgentFinished, EventKind

logger = logging.getLogger(__name__)

_TOAST_SCRIPT = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
    "ContentType = WindowsRuntime] | Out-Null; "
    "$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
    "$texts = $xml.GetElementsByTagName('text'); "
    "$texts.Item(0).AppendChild($xml.CreateTextNode($env:WG_TITLE)) | Out-Null; "
    "$texts.Item(1).AppendChild($xml.CreateTextNode($env:WG_BODY)) | Out-Null; "
    "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    "'VibeGap').Show($toast)"
)


class ToastNotifier:
    """把调度器效果翻译成 Windows toast(实现 daemon.runtime.Notifier 协议)。"""

    def show_window(self) -> None:
        self._toast("VibeGap", "agent is running - time for some words")

    def hide_window(self) -> None:
        logger.info("effect: hide window (noop in toast mode)")

    def show_banner(self, finished: AgentFinished) -> None:
        verb = "is waiting for you" if finished.kind is EventKind.ATTENTION else "finished"
        self._toast("VibeGap", f"{finished.agent.value} {verb}")

    def clear_banner(self) -> None:
        logger.info("effect: clear banner (noop in toast mode)")

    def show_summary(self) -> None:
        logger.info("effect: show summary (noop in toast mode)")

    def _toast(self, title: str, body: str) -> None:
        env = dict(os.environ, WG_TITLE=title, WG_BODY=body)
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", _TOAST_SCRIPT],
                env=env,
                timeout=TOAST_TIMEOUT_SEC,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("toast failed, falling back to log: %s | %s - %s", exc, title, body)
