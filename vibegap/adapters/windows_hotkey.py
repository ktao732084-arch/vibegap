"""Windows Shell Link 冷启动热键。

快捷方式由 Explorer 持有 Ctrl+Alt+W。目标是短命的 ``vibegap-ensure
--toggle``:VibeGap 不在时启动并显示,已在时只切换窗口。安装后主程序不再
调用 RegisterHotKey,避免两个拥有者争抢同一组合键。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_SHORTCUT_NAME = "VibeGap.lnk"
_HOTKEY = "CTRL+ALT+W"


def shortcut_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / _SHORTCUT_NAME


def is_installed(path: Path | None = None) -> bool:
    return (path or shortcut_path()).is_file()


def _target_command() -> tuple[str, str]:
    executable = shutil.which("vibegap-ensure.exe") or shutil.which("vibegap-ensure")
    if executable:
        return str(Path(executable).resolve()), "--toggle"
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    target = pythonw if os.name == "nt" and pythonw.is_file() else python
    return str(target.resolve()), "-m vibegap.adapters.hook --toggle"


def install(path: Path | None = None) -> Path:
    """创建 Start Menu 快捷方式;只在 Windows 上可用。"""
    if os.name != "nt":
        raise OSError("Windows Shell hotkeys are only available on Windows")
    destination = path or shortcut_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    target, arguments = _target_command()
    env = os.environ.copy()
    env.update(
        {
            "VIBEGAP_SHORTCUT_PATH": str(destination),
            "VIBEGAP_SHORTCUT_TARGET": target,
            "VIBEGAP_SHORTCUT_ARGUMENTS": arguments,
            "VIBEGAP_SHORTCUT_WORKDIR": str(Path(target).parent),
            "VIBEGAP_SHORTCUT_HOTKEY": _HOTKEY,
        }
    )
    script = (
        "$link=(New-Object -ComObject WScript.Shell).CreateShortcut($env:VIBEGAP_SHORTCUT_PATH);"
        "$link.TargetPath=$env:VIBEGAP_SHORTCUT_TARGET;"
        "$link.Arguments=$env:VIBEGAP_SHORTCUT_ARGUMENTS;"
        "$link.WorkingDirectory=$env:VIBEGAP_SHORTCUT_WORKDIR;"
        "$link.Description='VibeGap cold-start hotkey';"
        "$link.Hotkey=$env:VIBEGAP_SHORTCUT_HOTKEY;"
        "$link.WindowStyle=7;"
        "$link.Save()"
    )
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        check=True,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env=env,
    )
    if not destination.is_file():
        raise OSError(f"shortcut was not created: {destination}")
    return destination


def uninstall(path: Path | None = None) -> bool:
    destination = path or shortcut_path()
    try:
        destination.unlink()
        return True
    except FileNotFoundError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the VibeGap Windows hotkey")
    parser.add_argument("action", choices=("install", "uninstall", "status"))
    args = parser.parse_args()
    if args.action == "install":
        print(install())
    elif args.action == "uninstall":
        print("removed" if uninstall() else "not installed")
    else:
        print(shortcut_path() if is_installed() else "not installed")


if __name__ == "__main__":
    main()
