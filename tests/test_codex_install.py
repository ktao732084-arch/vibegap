"""Codex 官方 Hooks 安装器测试:merge、幂等、备份与干净卸载。"""
import importlib.util
from pathlib import Path

import pytest

_INSTALL_PATH = (
    Path(__file__).resolve().parent.parent
    / "vibegap" / "adapters" / "codex" / "install.py"
)
spec = importlib.util.spec_from_file_location("codex_install", _INSTALL_PATH)
codex_install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codex_install)

USER_HOOK = {
    "matcher": "*",
    "hooks": [{"type": "command", "command": "my-own-hook.exe"}],
}


def test_install_adds_root_and_subagent_lifecycle_hooks():
    result = codex_install.apply_install({})
    assert set(result["hooks"]) == {
        "SessionStart",
        "SessionEnd",
        "UserPromptSubmit",
        "Stop",
        "SubagentStart",
        "SubagentStop",
    }
    assert "--agent codex --event running" in result["hooks"]["SubagentStart"][0]["hooks"][0]["command"]
    assert "--agent codex --event done" in result["hooks"]["SubagentStop"][0]["hooks"][0]["command"]
    assert "--event attached" in result["hooks"]["SessionStart"][0]["hooks"][0]["command"]


def test_install_preserves_user_hooks_and_input():
    document = {"model": "gpt-5", "hooks": {"Stop": [USER_HOOK]}}
    result = codex_install.apply_install(document, port=9999)
    commands = [h["command"] for m in result["hooks"]["Stop"] for h in m["hooks"]]
    assert "my-own-hook.exe" in commands
    assert any("--event done --port 9999" in command for command in commands)
    assert document["hooks"]["Stop"] == [USER_HOOK]


def test_install_preserves_empty_or_metadata_only_user_matchers():
    user_matchers = [{"matcher": "review", "hooks": []}, {"matcher": "future"}]
    document = {"hooks": {"Stop": user_matchers}}
    installed = codex_install.apply_install(document)
    assert installed["hooks"]["Stop"][:2] == user_matchers
    assert codex_install.apply_uninstall(installed) == document


def test_install_is_idempotent_and_uninstall_restores_original():
    original = {"hooks": {"Stop": [USER_HOOK]}}
    installed = codex_install.apply_install(original)
    assert codex_install.apply_install(installed) == installed
    assert codex_install.apply_uninstall(installed) == original


def test_frozen_helper_command_is_installable_and_removable():
    prefix = '"C:\\Program Files\\VibeGap\\VibeGapHook.exe"'
    installed = codex_install.apply_install({}, helper_command=prefix)
    command = installed["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert command.startswith(prefix + " ")
    assert codex_install.apply_uninstall(installed) == {}


@pytest.mark.parametrize(
    "bad_document",
    [
        {"hooks": []},
        {"hooks": {"Stop": "not-a-list"}},
        {"hooks": {"Stop": [{"hooks": 42}]}},
    ],
)
def test_malformed_hooks_shape_is_rejected(bad_document):
    with pytest.raises(SystemExit):
        codex_install.validate_hooks_shape(bad_document)


def test_save_load_and_backup_roundtrip(tmp_path):
    path = tmp_path / "hooks.json"
    codex_install.save_hooks(path, {"hooks": {}})
    backup = codex_install.backup(path)
    assert backup is not None and backup.exists()
    assert codex_install.load_hooks(path) == {"hooks": {}}


def test_load_broken_hooks_refuses_to_clobber(tmp_path):
    path = tmp_path / "hooks.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(SystemExit):
        codex_install.load_hooks(path)
