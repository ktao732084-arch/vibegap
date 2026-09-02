"""冻结版 Agent 接入协调器。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibegap.adapters import packaged


def test_helper_command_quotes_installed_executable() -> None:
    command = packaged.helper_command(Path(r"C:\Program Files\VibeGap\VibeGap.exe"))
    assert command == '"C:\\Program Files\\VibeGap\\VibeGapHook.exe"'


def test_configure_claude_uses_absolute_frozen_command(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    executable = tmp_path / "VibeGap folder" / "VibeGap.exe"
    assert packaged.configure_agent("claude-code", executable, path=settings) is True
    document = json.loads(settings.read_text(encoding="utf-8"))
    command = document["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert str(executable.resolve().with_name("VibeGapHook.exe")) in command
    assert "--agent claude-code --event done" in command
    assert packaged.configure_agent(
        "claude-code", executable, path=settings, uninstall=True
    ) is True
    assert json.loads(settings.read_text(encoding="utf-8")) == {}


def test_configure_codex_is_idempotent(tmp_path: Path) -> None:
    hooks = tmp_path / "hooks.json"
    executable = tmp_path / "VibeGap.exe"
    assert packaged.configure_agent("codex", executable, path=hooks) is True
    assert packaged.configure_agent("codex", executable, path=hooks) is False


def test_configure_workbuddy_uses_its_agent_name(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    executable = tmp_path / "VibeGap.exe"
    assert packaged.configure_agent("workbuddy", executable, path=settings) is True
    document = json.loads(settings.read_text(encoding="utf-8"))
    command = document["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "--agent workbuddy --event done" in command


def test_receipt_only_matches_the_owned_agent_and_target(tmp_path: Path) -> None:
    receipt = tmp_path / "installer" / "codex.json"
    hooks = tmp_path / "hooks.json"
    packaged.write_receipt(receipt, "codex", hooks)
    assert packaged.receipt_matches(receipt, "codex", hooks)
    assert not packaged.receipt_matches(receipt, "claude-code", hooks)
    assert not packaged.receipt_matches(receipt, "codex", tmp_path / "other.json")


def test_missing_or_broken_receipt_never_claims_hooks(tmp_path: Path) -> None:
    receipt = tmp_path / "missing.json"
    assert not packaged.receipt_matches(receipt, "codex", tmp_path / "hooks.json")
    receipt.write_text("not json", encoding="utf-8")
    assert not packaged.receipt_matches(receipt, "codex", tmp_path / "hooks.json")


def test_remove_last_receipt_cleans_private_directory(tmp_path: Path) -> None:
    receipt = tmp_path / ".installer" / "codex.json"
    packaged.write_receipt(receipt, "codex", tmp_path / "hooks.json")
    packaged.remove_receipt(receipt)
    assert not receipt.parent.exists()


def test_uninstall_with_missing_receipt_never_touches_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected(*args, **kwargs):
        raise AssertionError("configure_agent must not run without an ownership receipt")

    monkeypatch.setattr(packaged, "configure_agent", unexpected)
    packaged.main(
        "uninstall-agent",
        [
            "codex",
            "--path",
            str(tmp_path / "hooks.json"),
            "--receipt",
            str(tmp_path / "missing.json"),
        ],
    )
    assert capsys.readouterr().out.strip() == "no owned hooks"
