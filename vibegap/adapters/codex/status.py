"""Read-only installation checks. Configuration is not proof of a working hook."""
from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path

from vibegap.adapters.codex import install


def inspect_hooks(path: Path, last_received: str | None = None) -> dict:
    result = {"agent": "codex"}
    if not path.parent.is_dir():
        return {**result, "status": "missing", "detail": "未检测到"}
    try:
        document = install.load_hooks(path)
        install.validate_hooks_shape(document)
    except (OSError, UnicodeError, SystemExit):
        return {**result, "status": "error", "detail": "配置无法读取，请检查 hooks.json；原文件未修改"}
    owned = {}
    for name in install.HOOK_EVENTS:
        owned[name] = [h for matcher in document.get("hooks", {}).get(name, [])
                       for h in matcher.get("hooks", []) if install._is_ours(h)]
    if not any(owned.values()):
        return {**result, "status": "available", "detail": "可接入官方 Hooks"}
    if not all(owned.values()):
        return {**result, "status": "available", "detail": "接入配置不完整，请重新接入"}
    for handlers in owned.values():
        for handler in handlers:
            command = handler.get("command")
            if handler.get("type") != "command" or not isinstance(command, str):
                return {**result, "status": "available", "detail": "接入命令无效，请重新接入"}
            try:
                words = shlex.split(command, posix=os.name != "nt")
                executable = words[0].strip('"') if words else ""
            except ValueError:
                executable = ""
            if not executable or shutil.which(executable) is None:
                return {**result, "status": "available", "detail": "找不到启动程序，请重新接入"}
    if last_received:
        return {**result, "status": "connected", "detail": "近期收到 Hook：" + last_received}
    return {**result, "status": "configured",
            "detail": "已配置，尚未验证本次连接；请在 Codex 审核信任后发送任务"}
