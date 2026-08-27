"""Claude Code 钩子安装器测试:merge 不覆盖 / 备份 / 干净卸载。"""
import importlib.util
import json
from pathlib import Path

import pytest

_INSTALL_PATH = (
    Path(__file__).resolve().parent.parent
    / "vibegap" / "adapters" / "claude_code" / "install.py"
)
spec = importlib.util.spec_from_file_location("cc_install", _INSTALL_PATH)
cc_install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc_install)

USER_HOOK = {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "my-own-linter.exe"}],
}


def test_install_into_empty_settings():
    result = cc_install.apply_install({}, "claude-code")
    assert set(result["hooks"]) == {
        "UserPromptSubmit", "Stop", "Notification", "SessionStart", "SessionEnd"
    }
    stop_cmd = result["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert stop_cmd.startswith("vibegap-hook ")
    assert "--agent claude-code" in stop_cmd
    assert "--event done" in stop_cmd
    assert '"' not in stop_cmd and "&" not in stop_cmd  # 任何 shell 下免转义
    assert "--event attached" in result["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "--event detached" in result["hooks"]["SessionEnd"][0]["hooks"][0]["command"]


def test_install_preserves_existing_user_hooks():
    settings = {
        "model": "opus",
        "hooks": {"Stop": [USER_HOOK]},
    }
    result = cc_install.apply_install(settings, "claude-code")
    assert result["model"] == "opus"
    stop_matchers = result["hooks"]["Stop"]
    commands = [h["command"] for m in stop_matchers for h in m["hooks"]]
    assert "my-own-linter.exe" in commands
    assert any("vibegap" in c.lower() for c in commands)
    assert settings["hooks"]["Stop"] == [USER_HOOK]  # 入参未被修改


def test_install_is_idempotent():
    once = cc_install.apply_install({}, "claude-code")
    twice = cc_install.apply_install(once, "claude-code")
    assert twice == once


def test_uninstall_removes_only_ours():
    settings = {"hooks": {"Stop": [USER_HOOK]}}
    installed = cc_install.apply_install(settings, "claude-code")
    restored = cc_install.apply_uninstall(installed)
    assert restored == settings


def test_uninstall_from_clean_settings_is_noop():
    settings = {"model": "opus"}
    assert cc_install.apply_uninstall(settings) == settings


def test_port_is_threaded_into_command():
    result = cc_install.apply_install({}, "claude-code", port=9999)
    cmd = result["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "--port 9999" in cmd


def test_default_port_present():
    result = cc_install.apply_install({}, "claude-code")
    cmd = result["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "--port 8765" in cmd


@pytest.mark.parametrize(
    "bad_settings",
    [
        {"hooks": []},                          # hooks 不是对象
        {"hooks": {"Stop": "not-a-list"}},      # 事件值不是列表
        {"hooks": {"Stop": [{"hooks": 42}]}},   # matcher.hooks 不是列表
    ],
)
def test_malformed_hooks_shape_exits_cleanly(bad_settings):
    with pytest.raises(SystemExit):
        cc_install.validate_hooks_shape(bad_settings)


def test_valid_hooks_shape_passes():
    cc_install.validate_hooks_shape({})
    cc_install.validate_hooks_shape({"hooks": {"Stop": [USER_HOOK]}})


def test_agent_override_for_dsh_bridge():
    result = cc_install.apply_install({}, "dsh")
    cmd = result["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "--agent dsh --event running" in cmd


def test_save_and_backup_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    cc_install.save_settings(path, {"hooks": {}})
    assert cc_install.backup(path) is not None
    assert len(list(tmp_path.glob("settings.json.bak.*"))) == 1
    loaded = cc_install.load_settings(path)
    assert loaded == {"hooks": {}}


def test_load_broken_settings_exits_instead_of_clobbering(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(SystemExit):
        cc_install.load_settings(path)
