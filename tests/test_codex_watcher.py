"""Codex 日志监听器单测(tmp 目录模拟 sessions 树)。"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from vibegap.daemon.codex_watcher import CodexWatcher

NOW = datetime(2026, 8, 26, 10, 0, 0)
SID = "01a01cca-2d01-7453-a9b1-9697616211d6"


def _day_dir(root: Path, day=26) -> Path:
    d = root / "2026" / "08" / f"{day:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _meta_line(sid=SID, cwd="E:\\proj", source=None) -> str:
    payload = {"session_id": sid, "cwd": cwd}
    if source is not None:
        payload["source"] = source
    return json.dumps({"type": "session_meta", "payload": payload})


def _event_line(payload_type: str) -> str:
    return json.dumps({"type": "event_msg", "payload": {"type": payload_type}})


def _make(tmp_path, clock=lambda: NOW):
    events = []
    watcher = CodexWatcher(
        tmp_path, emit=lambda sid, kind, cwd: events.append((sid, kind, cwd)), clock=clock
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


def test_preexisting_running_session_is_recovered(tmp_path):
    f = _day_dir(tmp_path) / f"rollout-x-{SID}.jsonl"
    f.write_text(_meta_line() + "\n" + _event_line("task_started") + "\n", encoding="utf-8")
    watcher, events = _make(tmp_path)
    watcher.poll()
    assert events == [(SID, "running", "E:\\proj")]
    with f.open("a", encoding="utf-8") as fh:
        fh.write(_event_line("task_complete") + "\n")
    watcher.poll()
    assert events[-1] == (SID, "done", "E:\\proj")


def test_preexisting_completed_session_is_not_recovered(tmp_path):
    f = _day_dir(tmp_path) / f"rollout-x-{SID}.jsonl"
    f.write_text(
        _meta_line() + "\n" + _event_line("task_started") + "\n" +
        _event_line("task_complete") + "\n",
        encoding="utf-8",
    )
    watcher, events = _make(tmp_path)
    watcher.poll()
    assert events == []


def test_active_session_from_old_creation_day_is_recovered(tmp_path):
    f = _day_dir(tmp_path, day=20) / f"rollout-x-{SID}.jsonl"
    f.write_text(_meta_line() + "\n" + _event_line("task_started") + "\n", encoding="utf-8")
    os.utime(f, (NOW.timestamp(), NOW.timestamp()))
    watcher, events = _make(tmp_path)
    watcher.poll()
    assert events == [(SID, "running", "E:\\proj")]


def test_old_session_resumed_after_start_is_discovered_without_full_replay(tmp_path):
    now = [NOW]
    f = _day_dir(tmp_path, day=20) / f"rollout-x-{SID}.jsonl"
    f.write_text(
        _meta_line() + "\n" + _event_line("task_complete") + "\n",
        encoding="utf-8",
    )
    old = (NOW - timedelta(hours=1)).timestamp()
    os.utime(f, (old, old))
    watcher, events = _make(tmp_path, clock=lambda: now[0])
    watcher.poll()
    assert events == []

    with f.open("a", encoding="utf-8") as fh:
        fh.write(_event_line("task_started") + "\n")
    now[0] += timedelta(seconds=6)
    os.utime(f, (now[0].timestamp(), now[0].timestamp()))
    watcher.poll()
    assert events == [(SID, "running", "E:\\proj")]

    with f.open("a", encoding="utf-8") as fh:
        fh.write(_event_line("task_complete") + "\n")
    watcher.poll()  # 已跟踪的历史文件每轮增量读取,不必等待下次全树发现
    assert events[-1] == (SID, "done", "E:\\proj")


def test_subagent_log_uses_file_uuid_instead_of_parent_session_id(tmp_path):
    child_sid = "02b12ddb-3e12-8564-b0c2-a708727322e7"
    f = _day_dir(tmp_path) / f"rollout-x-{child_sid}.jsonl"
    f.write_text(
        _meta_line(source={"subagent": {"kind": "spawn"}}) + "\n" +
        _event_line("task_started") + "\n",
        encoding="utf-8",
    )
    watcher, events = _make(tmp_path)
    watcher.poll()
    assert events == [(child_sid, "running", "E:\\proj")]


def test_recovery_scans_beyond_last_chunk(tmp_path):
    f = _day_dir(tmp_path) / f"rollout-x-{SID}.jsonl"
    noise = _event_line("token_count") + "\n"
    f.write_text(
        _meta_line() + "\n" + _event_line("task_started") + "\n" + noise * 6000,
        encoding="utf-8",
    )
    watcher, events = _make(tmp_path)
    watcher.poll()
    assert events == [(SID, "running", "E:\\proj")]


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
