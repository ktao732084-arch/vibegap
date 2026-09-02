"""跨 Agent 的瞬时 Hook helper 与按需启动器。

helper 一次性读入 Hook stdin。热路径直接 POST 后退出;连接失败时才启动
VibeGap、等待带身份的 /healthz 就绪,再重放同一份 payload。进程始终短命,
不引入新的常驻层。
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from vibegap.config import DAEMON_PORT, SERVICE_ID, SERVICE_PROTOCOL_VERSION

_HOST = "127.0.0.1"
_FAST_TIMEOUT_SEC = 0.35
_REQUEST_TIMEOUT_SEC = 1.0
_START_TIMEOUT_SEC = 8.0
_POLL_INTERVAL_SEC = 0.05
_MAX_PAYLOAD_BYTES = 1024 * 1024
_LIFECYCLE_EVENTS = {"attached", "detached"}
_HOOK_EVENTS = {"running", "done", "attention"}
_SERVICE_MATCH = "match"
_SERVICE_ABSENT = "absent"
_SERVICE_FOREIGN = "foreign"


def _read_payload() -> bytes:
    payload = sys.stdin.buffer.read(_MAX_PAYLOAD_BYTES + 1)
    if len(payload) > _MAX_PAYLOAD_BYTES:
        return b"{}"
    return payload or b"{}"


def _request(
    method: str,
    path: str,
    port: int,
    body: bytes | None = None,
    timeout: float = _REQUEST_TIMEOUT_SEC,
) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection(_HOST, port, timeout=timeout)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _service_status(port: int) -> str:
    try:
        status, raw = _request("GET", "/healthz", port, timeout=_FAST_TIMEOUT_SEC)
        if status != 200:
            return _SERVICE_FOREIGN
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return _SERVICE_FOREIGN
        matches = (
            payload.get("service") == SERVICE_ID
            and payload.get("protocol") == SERVICE_PROTOCOL_VERSION
        )
        return _SERVICE_MATCH if matches else _SERVICE_FOREIGN
    except (ValueError, http.client.HTTPException):
        return _SERVICE_FOREIGN
    except OSError:
        try:
            with socket.create_connection((_HOST, port), timeout=_FAST_TIMEOUT_SEC):
                return _SERVICE_FOREIGN
        except OSError:
            return _SERVICE_ABSENT


def _health_matches(port: int) -> bool:
    return _service_status(port) == _SERVICE_MATCH


def _post_event(agent: str, event: str, port: int, payload: bytes, timeout: float) -> bool:
    prefix = "lifecycle" if event in _LIFECYCLE_EVENTS else "hook"
    try:
        status, _ = _request(
            "POST",
            f"/{prefix}/{agent}/{event}",
            port,
            body=payload,
            timeout=timeout,
        )
        return 200 <= status < 300
    except (OSError, http.client.HTTPException):
        return False


def _daemon_command(port: int) -> list[str]:
    if getattr(sys, "frozen", False):
        executable = str(Path(sys.executable).with_name("VibeGap.exe"))
        return [executable, "--daemon", "--port", str(port)]
    return [sys.executable, "-m", "vibegap", "--port", str(port)]


def _launch_daemon(port: int) -> subprocess.Popen:
    command = _daemon_command(port)
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "env": os.environ.copy(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)  # noqa: S603 - 固定模块入口


def _ensure_started(port: int, timeout: float = _START_TIMEOUT_SEC) -> bool:
    status = _service_status(port)
    if status == _SERVICE_MATCH:
        return True
    if status == _SERVICE_FOREIGN:
        return False
    try:
        _launch_daemon(port)
    except OSError:
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = _service_status(port)
        if status == _SERVICE_MATCH:
            return True
        # 我们刚刚启动的进程会先 bind、后挂载 HTTP 路由。这个短窗口里端口
        # 已打开但 /healthz 尚不可读,不能误判成外来服务并丢掉首次事件。
        time.sleep(_POLL_INTERVAL_SEC)
    return False


def hook_main() -> None:
    """安装到 Agent hooks 的入口;任何故障都必须静默且 exit 0。"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--event", choices=sorted(_HOOK_EVENTS | _LIFECYCLE_EVENTS), required=True)
    parser.add_argument("--port", type=int, default=DAEMON_PORT)
    args = parser.parse_args()
    try:
        payload = _read_payload()
        if _post_event(args.agent, args.event, args.port, payload, _FAST_TIMEOUT_SEC):
            return
        # SessionEnd 是清理信号。Core 已经空闲退出时不能为了“通知它退出”
        # 反向把它重新拉起,否则闲置零进程永远无法成立。
        if args.event == "detached":
            return
        if _ensure_started(args.port):
            _post_event(args.agent, args.event, args.port, payload, _REQUEST_TIMEOUT_SEC)
    except Exception:
        # Hook 永远不能阻塞或破坏宿主 Agent。详细启动错误由 daemon.log 负责。
        return


def ensure_main() -> None:
    """用户/系统快捷方式入口:按需启动,可在就绪后切换悬浮窗。"""
    parser = argparse.ArgumentParser(description="Start VibeGap on demand")
    parser.add_argument("--port", type=int, default=DAEMON_PORT)
    parser.add_argument("--toggle", action="store_true")
    args = parser.parse_args()
    if not _ensure_started(args.port):
        raise SystemExit("VibeGap could not start; check ~/.vibegap/logs/daemon.log")
    if args.toggle:
        try:
            status, _ = _request("POST", "/toggle", args.port, body=b"{}")
        except (OSError, http.client.HTTPException) as exc:
            raise SystemExit(f"VibeGap started but could not toggle: {exc}") from exc
        if not 200 <= status < 300:
            raise SystemExit(f"VibeGap toggle failed with HTTP {status}")


if __name__ == "__main__":
    # ``vibegap-hook`` has its own console entry point. Module execution is the
    # dependency-free fallback used by the optional Windows shortcut.
    ensure_main()
