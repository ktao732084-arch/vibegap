"""Codex 会话日志监听:零配置适配。

不写 ~/.codex/config.toml 的 notify(实测已被 Codex Desktop 自身占用,覆盖会破坏
桌面端功能)。改为增量追踪 sessions/YYYY/MM/DD/*.jsonl:
  event_msg.payload.type == task_started               -> running
  event_msg.payload.type in (task_complete, turn_aborted) -> done
session_id 取自文件名 uuid,cwd 取自首行 session_meta。
守护进程启动时会反向查找每个文件最后一条生命周期事件,只恢复仍在运行的
任务;随后 offset 置为文件尾,继续增量处理新增内容。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from vibegap.config import CODEX_WATCH_DAYS

logger = logging.getLogger(__name__)

_RUNNING_TYPES = ("task_started",)
_DONE_TYPES = ("task_complete", "turn_aborted")
_SID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_REVERSE_READ_BYTES = 64 * 1024

# emit(session_id, kind, cwd),kind 为 "running" | "done"
EmitFn = Callable[[str, str, str], None]


class CodexWatcher:
    """增量读取 codex 会话日志并上报生命周期事件。poll() 由 ticker 周期调用。"""

    def __init__(
        self,
        sessions_dir: Path,
        emit: EmitFn,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._dir = Path(sessions_dir)
        self._emit = emit
        self._clock = clock
        self._offsets: dict[Path, int] = {}
        self._meta: dict[Path, tuple[str, str]] = {}  # path -> (session_id, cwd)
        self._is_first_poll = True

    def poll(self) -> None:
        """扫描最近日期目录下的会话文件,处理新增行。所有异常吞掉只记日志。"""
        for path in self._recent_files():
            try:
                self._read_new_lines(path)
            except OSError as exc:
                logger.debug("codex watcher read failed %s: %s", path.name, exc)
        self._is_first_poll = False

    def _recent_files(self):
        today = self._clock().date()
        for delta in range(CODEX_WATCH_DAYS):
            day = today - timedelta(days=delta)
            folder = self._dir / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
            if folder.is_dir():
                yield from folder.glob("*.jsonl")

    def _read_new_lines(self, path: Path) -> None:
        size = path.stat().st_size
        if path not in self._offsets:
            # 启动前已存在的文件跳过旧内容;监听期间新出现的文件从头处理
            self._register_file(path, size, replay=not self._is_first_poll)
        offset = self._offsets[path]
        if size <= offset:
            return
        with path.open("rb") as fh:
            fh.seek(offset)
            chunk = fh.read(size - offset)
        consumed = chunk.rfind(b"\n") + 1  # 只消费完整行,残行等下次
        if consumed <= 0:
            return
        self._offsets[path] = offset + consumed
        for raw in chunk[:consumed].splitlines():
            self._handle_line(path, raw)

    def _register_file(self, path: Path, size: int, replay: bool) -> None:
        """首次见到文件:读取元数据;首轮恢复最终运行态,新文件从头回放。"""
        sid_match = _SID_RE.search(path.name)
        file_session_id = sid_match.group(1) if sid_match else path.stem
        session_id = file_session_id
        cwd = ""
        is_subagent = False
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                first = json.loads(fh.readline() or "{}")
            if first.get("type") == "session_meta":
                payload = first.get("payload") or {}
                cwd = str(payload.get("cwd", ""))
                source = payload.get("source") or {}
                is_subagent = isinstance(source, dict) and "subagent" in source
                if not is_subagent:
                    session_id = str(payload.get("session_id") or session_id)
        except (OSError, json.JSONDecodeError):
            pass
        self._meta[path] = (session_id, cwd)
        self._offsets[path] = 0 if replay else size
        if not replay and self._last_lifecycle(path) == "running":
            self._emit(session_id, "running", cwd)
        logger.info(
            "codex watcher tracking %s (sid=%s, subagent=%s)",
            path.name,
            session_id[:8],
            is_subagent,
        )

    def _last_lifecycle(self, path: Path) -> str | None:
        """从文件尾反向查找最近生命周期事件,避免启动时回放整份日志。"""
        try:
            with path.open("rb") as fh:
                position = fh.seek(0, 2)
                carry = b""
                while position > 0:
                    read_size = min(_REVERSE_READ_BYTES, position)
                    position -= read_size
                    fh.seek(position)
                    carry = fh.read(read_size) + carry
                    lines = carry.split(b"\n")
                    carry = lines[0]
                    for raw in reversed(lines[1:]):
                        kind = _lifecycle_kind(raw)
                        if kind is not None:
                            return kind
                return _lifecycle_kind(carry)
        except OSError as exc:
            logger.debug("codex watcher recovery failed %s: %s", path.name, exc)
            return None

    def _handle_line(self, path: Path, raw: bytes) -> None:
        kind = _lifecycle_kind(raw)
        if kind is None:
            return
        session_id, cwd = self._meta.get(path, (path.stem, ""))
        self._emit(session_id, kind, cwd)


def _lifecycle_kind(raw: bytes) -> str | None:
    """解析单行 Codex 日志,仅返回 VibeGap 关心的生命周期状态。"""
    if not any(token.encode() in raw for token in _RUNNING_TYPES + _DONE_TYPES):
        return None
    try:
        record = json.loads(raw.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None
    if record.get("type") != "event_msg":
        return None
    payload_type = (record.get("payload") or {}).get("type")
    if payload_type in _RUNNING_TYPES:
        return "running"
    if payload_type in _DONE_TYPES:
        return "done"
    return None
