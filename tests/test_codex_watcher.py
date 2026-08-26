"""Codex 日志监听器单测(tmp 目录模拟 sessions 树)。"""
import json
from datetime import datetime
from pathlib import Path

from wordgap.daemon.codex_watcher import CodexWatcher

NOW = datetime(2026, 8, 26, 10, 0, 0)
SID = "01a01cca-2d01-7453-a9b1-9697616211d6"


def _day_dir(root: Path) -> Path:
    d = root / "2026" / "08" / "26"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _meta_line(sid=SID, cwd="E:\\proj") -> str:
    return json.dumps(
        {"type": "session_meta", "payload": {"session_id": sid, "cwd": cwd}}
    )


def _event_line(payload_type: str) -> str:
    return json.dumps({"type": "event_msg", "payload": {"type": payload_type}})


def _make(tmp_path):
    events = []
    watcher = CodexWatcher(
        tmp_path, emit=lambda sid, kind, cwd: events.append((sid, kind, cwd)), clock=lambda: NOW
    )
    return watcher, events


def test_new_file_during_watch_is_processed_from_start(tmp_path):
    watcher, events = _make(tmp_path)
    watcher.poll()  # 空目录首轮
    f = _day_dir(tmp_path) / f"rollout-2026-08-26T10-00-00-{SID}.jsonl"
    f.write_text(_meta_line() + "\n" + _event_line("task_started") + "\n", encoding="utf-8")
    watcher.poll()
    assert events == [(SID, "running", "E:\\proj")]
    with f.open("a", encoding="utf-8") as fh:
        fh.write(_event_line("task_complete") + "\n")
    watcher.poll()
    assert events[-1] == (SID, "done", "E:\\proj")


def test_preexisting_content_not_replayed(tmp_path):
    f = _day_dir(tmp_path) / f"rollout-x-{SID}.jsonl"
    f.write_text(_meta_line() + "\n" + _event_line("task_started") + "\n", encoding="utf-8")
    watcher, events = _make(tmp_path)
    watcher.poll()
    assert events == []  # 旧内容跳过
    with f.open("a", encoding="utf-8") as fh:
        fh.write(_event_line("task_complete") + "\n")
    watcher.poll()
    assert events == [(SID, "done", "E:\\proj")]  # 新增行照常处理,且 meta 已读到


def test_turn_aborted_counts_as_done(tmp_path):
    watcher, events = _make(tmp_path)
    watcher.poll()
    f = _day_dir(tmp_path) / f"a-{SID}.jsonl"
    f.write_text(_event_line("turn_aborted") + "\n", encoding="utf-8")
    watcher.poll()
    assert events == [(SID, "done", "")]


def test_partial_line_buffered_until_complete(tmp_path):
    watcher, events = _make(tmp_path)
    watcher.poll()
    f = _day_dir(tmp_path) / f"a-{SID}.jsonl"
    full = _event_line("task_started")
    f.write_text(full[:20], encoding="utf-8")  # 写了半行
    watcher.poll()
    assert events == []
    with f.open("a", encoding="utf-8") as fh:
        fh.write(full[20:] + "\n")
    watcher.poll()
    assert events == [(SID, "running", "")]


def test_garbage_lines_ignored(tmp_path):
    watcher, events = _make(tmp_path)
    watcher.poll()
    f = _day_dir(tmp_path) / f"a-{SID}.jsonl"
    f.write_text("{broken json\n" + _event_line("token_count") + "\n", encoding="utf-8")
    watcher.poll()
    assert events == []


def test_missing_sessions_dir_is_harmless(tmp_path):
    watcher, events = _make(tmp_path / "nonexistent")
    watcher.poll()
    assert events == []
