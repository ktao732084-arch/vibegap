"""安装 VibeGap Codex 生命周期 Hooks,merge 写入 ~/.codex/hooks.json。

不修改 Codex 的 notify 配置。安装遵循 merge、备份、可卸载三原则。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_PORT = 8765
_MARKERS = ("vibegap-hook", "src=vibegap", "src=wordgap")
HOOK_EVENTS = {
    "SessionStart": "attached",
    "SessionEnd": "detached",
    "UserPromptSubmit": "running",
    "Stop": "done",
    "SubagentStart": "running",
    "SubagentStop": "done",
}


def build_command(event: str, port: int = DEFAULT_PORT) -> str:
    """生成瞬时 helper 命令;冷启动后仍能重放原始 Hook payload。"""
    return f"vibegap-hook --agent codex --event {event} --port {port}"


def load_hooks(path: Path) -> dict:
    """读取 hooks.json;文件不存在时返回空对象,损坏时拒绝覆盖。"""
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: {path} is not valid JSON ({exc}); fix it manually first.")
    if not isinstance(loaded, dict):
        sys.exit(f"ERROR: {path} must contain a JSON object.")
    return loaded


def validate_hooks_shape(document: dict) -> None:
    """校验 Codex hooks.json 的三层对象/数组结构。"""
    hooks = document.get("hooks")
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        sys.exit("ERROR: 'hooks' must be an object.")
    for name, matchers in hooks.items():
        if not isinstance(matchers, list) or not all(isinstance(m, dict) for m in matchers):
            sys.exit(f"ERROR: hooks['{name}'] must be a list of objects.")
        for matcher in matchers:
            handlers = matcher.get("hooks", [])
            if not isinstance(handlers, list) or not all(isinstance(h, dict) for h in handlers):
                sys.exit(f"ERROR: a matcher in hooks['{name}'] has invalid handlers.")


def apply_install(document: dict, port: int = DEFAULT_PORT) -> dict:
    """返回合入 VibeGap Hooks 后的新文档,不修改入参。"""
    result = json.loads(json.dumps(document))
    hooks = result.setdefault("hooks", {})
    for name, event in HOOK_EVENTS.items():
        matchers = _strip_ours(hooks.get(name, []))
        matchers.append(
            {"hooks": [{"type": "command", "command": build_command(event, port)}]}
        )
        hooks[name] = matchers
    return result


def apply_uninstall(document: dict) -> dict:
    """只移除 VibeGap 写入的 handlers,保留用户与其他插件配置。"""
    result = json.loads(json.dumps(document))
    hooks = result.get("hooks", {})
    for name in list(hooks):
        hooks[name] = _strip_ours(hooks[name])
        if not hooks[name]:
            del hooks[name]
    if "hooks" in result and not result["hooks"]:
        del result["hooks"]
    return result


def backup(path: Path) -> Path | None:
    """写前创建不会重名的时间戳备份。"""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = path.with_name(f"{path.name}.bak.{stamp}")
    shutil.copy2(path, target)
    return target


def save_hooks(path: Path, document: dict) -> None:
    """以 UTF-8 写回 Codex hooks.json。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _strip_ours(matchers: list) -> list:
    kept = []
    for matcher in matchers:
        original = matcher.get("hooks", [])
        handlers = [h for h in original if not _is_ours(h)]
        if handlers == original:
            kept.append(matcher)
            continue
        if handlers:
            kept.append({**matcher, "hooks": handlers})
    return kept


def _is_ours(handler: dict) -> bool:
    command = str(handler.get("command", "")).lower()
    return any(marker in command for marker in _MARKERS)


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="Install VibeGap hooks for Codex")
    parser.add_argument("--hooks", type=Path, default=Path.home() / ".codex" / "hooks.json")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    document = load_hooks(args.hooks)
    validate_hooks_shape(document)
    updated = apply_uninstall(document) if args.uninstall else apply_install(document, args.port)
    if updated == document:
        print("No changes needed.")
        return
    backup_path = backup(args.hooks)
    save_hooks(args.hooks, updated)
    action = "Uninstalled from" if args.uninstall else "Installed to"
    print(f"{action} {args.hooks}")
    if backup_path:
        print(f"Backup: {backup_path}")
    if not args.uninstall:
        print("Open Codex /hooks to review and trust the new hooks.")


if __name__ == "__main__":
    main()
