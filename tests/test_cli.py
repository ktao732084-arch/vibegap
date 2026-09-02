"""统一源码/冻结版命令分发。"""
from vibegap import cli


def test_default_and_explicit_daemon_modes() -> None:
    assert cli.split_mode([]) == ("daemon", [])
    assert cli.split_mode(["--port", "9999"]) == ("daemon", ["--port", "9999"])
    assert cli.split_mode(["--daemon", "--port", "9999"]) == (
        "daemon",
        ["--port", "9999"],
    )


def test_helper_and_installer_modes_strip_dispatch_flag() -> None:
    assert cli.split_mode(["--ensure", "--toggle"]) == ("ensure", ["--toggle"])
    assert cli.split_mode(["--install-agent", "codex"]) == (
        "install-agent",
        ["codex"],
    )
    assert cli.split_mode(["--uninstall-agent", "claude-code"]) == (
        "uninstall-agent",
        ["claude-code"],
    )
