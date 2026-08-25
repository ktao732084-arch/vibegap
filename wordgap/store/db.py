"""SQLite 连接管理与建表。SQL 只允许出现在 store/ (§7.2)。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wordbook (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    word_count  INTEGER NOT NULL,
    words_json  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    wordbook_id  INTEGER PRIMARY KEY REFERENCES wordbook(id),
    mode         TEXT NOT NULL CHECK (mode IN ('sequential','shuffled')),
    shuffle_seed INTEGER,
    cursor       INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS word_log (
    id           INTEGER PRIMARY KEY,
    wordbook_id  INTEGER NOT NULL REFERENCES wordbook(id),
    word_index   INTEGER NOT NULL,
    word         TEXT NOT NULL,
    result       TEXT NOT NULL CHECK (result IN ('pass','fail','skip')),
    typo_count   INTEGER NOT NULL DEFAULT 0,
    seen_at      TEXT NOT NULL,
    stability    REAL,
    difficulty   REAL,
    due_at       TEXT
);

CREATE TABLE IF NOT EXISTS session_stat (
    id          INTEGER PRIMARY KEY,
    agent       TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    words_done  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """打开(必要时创建)数据库并保证 schema 就绪。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init_schema(conn)
    return conn


def kv_get(conn: sqlite3.Connection, key: str) -> str | None:
    """读全局键值,不存在返回 None。"""
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return None if row is None else row["value"]


def kv_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    """写全局键值(upsert)。"""
    conn.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    if kv_get(conn, "schema_version") is None:
        kv_set(conn, "schema_version", str(SCHEMA_VERSION))
