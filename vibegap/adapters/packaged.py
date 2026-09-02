"""冻结版安装器调用的 Agent Hook 配置协调器。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from vibegap.adapters.claude_code import install as claude_install
from vibegap.adapters.codex import install as codex_install
from vibegap.config import DAEMON_PORT

_AGENTS = ("claude-code", "codex", "workbuddy")


def helper_command(executable: Path) -> str:
    """生成不依赖 PATH、可安全包含空格的 Windows Hook 前缀。"""
    hook_executable = executable.resolve().with_name("VibeGapHook.exe")
    return subprocess.list2cmdline([str(hook_executable)])


def default_path(agent: str) -> Path:
    if agent == "claude-code":
        return Path.home() / ".claude" / "settings.json"
    if agent == "codex":
        return Path.home() / ".codex" / "hooks.json"
    if agent == "workbuddy":
        return Path.home() / ".workbuddy-ai" / "settings.json"
    raise ValueError(f"unsupported agent: {agent}")


def write_receipt(path: Path, agent: str, target: Path) -> None:
    """记录安装器实际拥有的 Hook，供卸载时做精确边界判断。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"agent": agent, "target": str(target.resolve())},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def receipt_matches(path: Path, agent: str, target: Path) -> bool:
    """收据缺失或损坏时宁可保留 Hook，也不误删其他安装方式的配置。"""
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return receipt == {"agent": agent, "target": str(target.resolve())}


def remove_receipt(path: Path) -> None:
    """删除收据，并在最后一个集成卸载后清掉空的私有目录。"""
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def configure_agent(
    agent: str,
    executable: Path,
    *,
    path: Path | None = None,
    port: int = DAEMON_PORT,
    uninstall: bool = False,
) -> bool:
    """合入或移除一个 Agent 的冻结版 Hook;返回是否写盘。"""
    target = path or default_path(agent)
    if agent in {"claude-code", "workbuddy"}:
        document = claude_install.load_settings(target)
        claude_install.validate_hooks_shape(document)
        updated = (
            claude_install.apply_uninstall(document)
            if uninstall
            else claude_install.apply_install(
                document,
                agent,
                port,
                helper_command(executable),
            )
        )
        writer = claude_install.save_settings
        backup = claude_install.backup
    elif agent == "codex":
        document = codex_install.load_hooks(target)
        codex_install.validate_hooks_shape(document)
        updated = (
            codex_install.apply_uninstall(document)
            if uninstall
            else codex_install.apply_install(
                document,
                port,
                helper_command(executable),
            )
        )
        writer = codex_install.save_hooks
        backup = codex_install.backup
    else:
        raise ValueError(f"unsupported agent: {agent}")
    if updated == document:
        return False
    backup(target)
    writer(target, updated)
    return True


def main(action: str, argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Configure VibeGap Agent hooks")
    parser.add_argument("agent", choices=_AGENTS)
    parser.add_argument("--port", type=int, default=DAEMON_PORT)
    parser.add_argument("--path", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    target = args.path or default_path(args.agent)
    uninstall = action == "uninstall-agent"
    if uninstall and args.receipt is not None and not receipt_matches(
        args.receipt, args.agent, target
    ):
        print("no owned hooks")
        return
    changed = configure_agent(
        args.agent,
        Path(sys.executable),
        path=target,
        port=args.port,
        uninstall=uninstall,
    )
    if args.receipt is not None:
        if uninstall:
            remove_receipt(args.receipt)
        else:
            write_receipt(args.receipt, args.agent, target)
    print("updated" if changed else "no changes")
