"""词书导入与查询(qwerty-learner JSON 格式)。"""
from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from wordgap.config import MODE_SHUFFLED, SEED_RANGE, VALID_MODES
from wordgap.store.db import kv_get, kv_set

_CURRENT_KEY = "current_wordbook"


class WordbookError(ValueError):
    """词书数据非法或操作失败。"""


@dataclass(frozen=True)
class Word:
    name: str
    trans: tuple[str, ...]
    usphone: str


@dataclass(frozen=True)
class Wordbook:
    id: int
    name: str
    word_count: int


def import_wordbook(
    conn: sqlite3.Connection,
    name: str,
    words_raw: list[dict],
    mode: str = "shuffled",
    seed: int | None = None,
    now: datetime | None = None,
) -> Wordbook:
    """导入词书并建进度行。任何词条非法则整体失败,不入库。"""
    if mode not in VALID_MODES:
        raise WordbookError(f"unknown mode: {mode}")
    words = _validate_words(words_raw)
    created_at = (now or datetime.now()).isoformat(timespec="seconds")
    shuffle_seed = _resolve_seed(mode, seed)
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO wordbook (name, word_count, words_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (name, len(words), json.dumps(words_raw, ensure_ascii=False), created_at),
            )
            wordbook_id = cur.lastrowid
            conn.execute(
                "INSERT INTO progress (wordbook_id, mode, shuffle_seed, cursor, updated_at) "
                "VALUES (?, ?, ?, 0, ?)",
                (wordbook_id, mode, shuffle_seed, created_at),
            )
    except sqlite3.IntegrityError as exc:
        raise WordbookError(f"wordbook '{name}' already exists") from exc
    return Wordbook(id=wordbook_id, name=name, word_count=len(words))


def import_wordbook_file(
    conn: sqlite3.Connection,
    path: Path,
    name: str | None = None,
    mode: str = "shuffled",
    seed: int | None = None,
) -> Wordbook:
    """从 qwerty-learner JSON 文件导入;name 缺省用文件名。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WordbookError(f"cannot read wordbook file {path}: {exc}") from exc
    return import_wordbook(conn, name or path.stem, raw, mode=mode, seed=seed)


def get_words(conn: sqlite3.Connection, wordbook_id: int) -> tuple[Word, ...]:
    """取词书全部词条(按原始顺序)。"""
    row = conn.execute(
        "SELECT words_json FROM wordbook WHERE id = ?", (wordbook_id,)
    ).fetchone()
    if row is None:
        raise WordbookError(f"wordbook {wordbook_id} not found")
    return tuple(_to_word(item) for item in json.loads(row["words_json"]))


def list_wordbooks(conn: sqlite3.Connection) -> list[Wordbook]:
    """列出全部词书。"""
    rows = conn.execute("SELECT id, name, word_count FROM wordbook ORDER BY id").fetchall()
    return [Wordbook(id=r["id"], name=r["name"], word_count=r["word_count"]) for r in rows]


def set_current(conn: sqlite3.Connection, wordbook_id: int) -> None:
    """设为当前词书(kv)。"""
    if conn.execute("SELECT 1 FROM wordbook WHERE id = ?", (wordbook_id,)).fetchone() is None:
        raise WordbookError(f"wordbook {wordbook_id} not found")
    kv_set(conn, _CURRENT_KEY, str(wordbook_id))


def get_current(conn: sqlite3.Connection) -> int | None:
    """当前词书 id;未设置返回 None。"""
    value = kv_get(conn, _CURRENT_KEY)
    return None if value is None else int(value)


def _validate_words(words_raw: object) -> list[dict]:
    if not isinstance(words_raw, list) or not words_raw:
        raise WordbookError("wordbook must be a non-empty JSON array")
    for i, item in enumerate(words_raw):
        if not isinstance(item, dict):
            raise WordbookError(f"entry {i} is not an object")
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            raise WordbookError(f"entry {i} missing non-empty 'name'")
        if not isinstance(item.get("trans"), list) or not item["trans"]:
            raise WordbookError(f"entry {i} missing non-empty 'trans' list")
    return words_raw


def _to_word(item: dict) -> Word:
    return Word(
        name=item["name"],
        trans=tuple(str(t) for t in item["trans"]),
        usphone=str(item.get("usphone", "")),
    )


def _resolve_seed(mode: str, seed: int | None) -> int | None:
    if mode != MODE_SHUFFLED:
        return None
    return seed if seed is not None else random.randrange(SEED_RANGE)
