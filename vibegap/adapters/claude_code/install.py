"""VibeGap 的 Claude Code 钩子安装器(独立脚本,不 import 主包,§7.2)。

用法:
    python install.py            # 安装到 ~/.claude/settings.json
    python install.py --uninstall
    python install.py --settings <path>   # 指定 settings 文件(测试/WorkBuddy 复用)
    python install.py --agent dsh         # 上报的 agent 名(dsh hook bridge 复用)

三原则(spec §7.8):merge 不覆盖、写前备份、可干净卸载。
识别标记:command 中含 "vibegap" 的钩子条目视为本工具写入。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

MARKER = "vibegap"
_LEGACY_MARKERS = ("vibegap", "wordgap")  # 项目曾名 wordgap,旧钩子也要能识别/卸载
DEFAULT_PORT = 8765  # 与主包 config.DAEMON_PORT 一致;adapter 零依赖故重复定义(spec §7.2)
HOOK_EVENTS = {
    "UserPromptSubmit": "running",
    "Stop": "done",
    "Notification": "attention",
    "SessionStart": "attached",
    "SessionEnd": "detached",
}


def build_command(
    event: str,
    agent: str,
    port: int = DEFAULT_PORT,
    helper_command: str = "vibegap-hook",
) -> str:
    """生成瞬时 helper 命令;helper 持有 stdin,失败时可启动并精确重放。"""
    return f"{helper_command} --agent {agent} --event {event} --port {port}"


def load_settings(path: Path) -> dict:
    """读 settings.json;不存在返回空对象,损坏则报错退出(绝不覆盖坏文件)。"""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: {path} is not valid JSON ({exc}); fix it manually first.")


def backup(path: Path) -> Path | None:
    """写前备份,返回备份路径。"""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.bak.{stamp}")
    shutil.copy2(path, target)
    return target


def _is_ours(hook_entry: dict) -> bool:
    command = str(hook_entry.get("command", "")).lower()
    return any(marker in command for marker in _LEGACY_MARKERS)


def _strip_ours(matchers: list) -> list:
    """从某事件的 matcher 列表中移除本工具的钩子,保留用户自己的。"""
    kept_matchers = []
    for matcher in matchers:
        hooks = [h for h in matcher.get("hooks", []) if not _is_ours(h)]
        if hooks or any(k for k in matcher if k != "hooks"):
            kept_matchers.append({**matcher, "hooks": hooks} if hooks else matcher)
    return [m for m in kept_matchers if m.get("hooks")]


def validate_hooks_shape(settings: dict) -> None:
    """settings.hooks 结构不合预期时给出友好报错(而非深处 traceback)。"""
    hooks = settings.get("hooks")
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        sys.exit("ERROR: settings 'hooks' must be an object; fix it manually first.")
    for name, matchers in hooks.items():
        if not isinstance(matchers, list) or not all(isinstance(m, dict) for m in matchers):
            sys.exit(f"ERROR: settings hooks['{name}'] must be a list of objects.")
        for matcher in matchers:
            if "hooks" in matcher and not isinstance(matcher["hooks"], list):
                sys.exit(f"ERROR: a matcher in hooks['{name}'] has non-list 'hooks'.")


def apply_install(
    settings: dict,
    agent: str,
    port: int = DEFAULT_PORT,
    helper_command: str = "vibegap-hook",
) -> dict:
    """返回合入 vibegap 钩子后的新 settings(不修改入参)。"""
    result = json.loads(json.dumps(settings))  # deep copy
    hooks = result.setdefault("hooks", {})
    for hook_name, event in HOOK_EVENTS.items():
        matchers = _strip_ours(hooks.get(hook_name, []))
        matchers.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": build_command(event, agent, port, helper_command),
                    }
                ]
            }
        )
        hooks[hook_name] = matchers
    return result


def apply_uninstall(settings: dict) -> dict:
    """返回移除 vibegap 钩子后的新 settings。"""
    result = json.loads(json.dumps(settings))
    hooks = result.get("hooks", {})
    for hook_name in list(hooks):
        hooks[hook_name] = _strip_ours(hooks[hook_name])
        if not hooks[hook_name]:
            del hooks[hook_name]
    if "hooks" in result and not result["hooks"]:
        del result["hooks"]
    return result


def save_settings(path: Path, settings: dict) -> None:
    """UTF-8 写回,保留中文可读。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Install VibeGap hooks for Claude Code")
    parser.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    parser.add_argument("--agent", default="claude-code")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    settings = load_settings(args.settings)
    validate_hooks_shape(settings)
    updated = (
        apply_uninstall(settings)
        if args.uninstall
        else apply_install(settings, args.agent, args.port)
    )
    if updated == settings:
        print("No changes needed.")
        return
    backup_path = backup(args.settings)
    save_settings(args.settings, updated)
    action = "Uninstalled from" if args.uninstall else "Installed to"
    print(f"{action} {args.settings}")
    if backup_path:
        print(f"Backup: {backup_path}")


if __name__ == "__main__":
    main()
