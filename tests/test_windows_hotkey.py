"""Windows Shell Link 管理逻辑;不修改真实 Start Menu。"""
from pathlib import Path

from vibegap.adapters import windows_hotkey


def test_install_builds_shortcut_with_expected_hotkey(tmp_path, monkeypatch):
    destination = tmp_path / "VibeGap.lnk"
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        destination.write_bytes(b"shortcut")

    monkeypatch.setattr(windows_hotkey.os, "name", "nt")
    monkeypatch.setattr(windows_hotkey, "_target_command", lambda: ("C:/bin/vibegap-ensure.exe", "--toggle"))
    monkeypatch.setattr(windows_hotkey.subprocess, "run", fake_run)

    assert windows_hotkey.install(destination) == destination
    command = calls[0][0]
    assert "powershell.exe" == command[0]
    env = calls[0][1]["env"]
    assert env["VIBEGAP_SHORTCUT_PATH"] == str(destination)
    assert env["VIBEGAP_SHORTCUT_HOTKEY"] == "CTRL+ALT+W"
    assert env["VIBEGAP_SHORTCUT_ARGUMENTS"] == "--toggle"


def test_uninstall_is_idempotent(tmp_path):
    destination = tmp_path / "VibeGap.lnk"
    destination.write_bytes(b"shortcut")
    assert windows_hotkey.uninstall(destination) is True
    assert windows_hotkey.uninstall(destination) is False
    assert windows_hotkey.is_installed(destination) is False


def test_target_falls_back_to_module_ensure_entry(tmp_path, monkeypatch):
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    python.write_bytes(b"")
    pythonw.write_bytes(b"")
    monkeypatch.setattr(windows_hotkey.shutil, "which", lambda command: None)
    monkeypatch.setattr(windows_hotkey.sys, "executable", str(python))
    monkeypatch.setattr(windows_hotkey.os, "name", "nt")

    assert windows_hotkey._target_command() == (
        str(pythonw.resolve()),
        "-m vibegap.adapters.hook --toggle",
    )
