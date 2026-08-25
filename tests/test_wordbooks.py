"""词书导入与查询单测。"""
import json

import pytest

from wordgap.store.db import connect
from wordgap.store.wordbooks import (
    WordbookError,
    get_current,
    get_words,
    import_wordbook,
    import_wordbook_file,
    list_wordbooks,
    set_current,
)

VALID_WORDS = [
    {"name": "abandon", "trans": ["放弃"], "usphone": "ə'bændən"},
    {"name": "ability", "trans": ["能力"], "usphone": "ə'bɪləti"},
    {"name": "able", "trans": ["能够的"]},
]


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def test_import_and_get_words(conn):
    book = import_wordbook(conn, "cet6", VALID_WORDS, seed=42)
    assert book.word_count == 3
    words = get_words(conn, book.id)
    assert [w.name for w in words] == ["abandon", "ability", "able"]
    assert words[0].trans == ("放弃",)
    assert words[2].usphone == ""  # usphone 缺省容忍


def test_import_creates_progress_row(conn):
    book = import_wordbook(conn, "cet6", VALID_WORDS, mode="shuffled", seed=42)
    row = conn.execute(
        "SELECT mode, shuffle_seed, cursor FROM progress WHERE wordbook_id = ?", (book.id,)
    ).fetchone()
    assert row["mode"] == "shuffled"
    assert row["shuffle_seed"] == 42
    assert row["cursor"] == 0


def test_sequential_mode_has_no_seed(conn):
    book = import_wordbook(conn, "cet6", VALID_WORDS, mode="sequential")
    row = conn.execute(
        "SELECT shuffle_seed FROM progress WHERE wordbook_id = ?", (book.id,)
    ).fetchone()
    assert row["shuffle_seed"] is None


@pytest.mark.parametrize(
    "bad",
    [
        [],                                        # 空词书
        "not a list",                              # 不是数组
        [{"trans": ["放弃"]}],                      # 缺 name
        [{"name": "", "trans": ["放弃"]}],          # 空 name
        [{"name": "abandon"}],                     # 缺 trans
        [{"name": "abandon", "trans": []}],        # 空 trans
        [{"name": "abandon", "trans": "放弃"}],     # trans 不是列表
        [{"name": "a", "trans": ["x"]}, 42],       # 词条不是对象
    ],
)
def test_malformed_wordbook_rejected_and_nothing_inserted(conn, bad):
    with pytest.raises(WordbookError):
        import_wordbook(conn, "bad", bad)
    assert list_wordbooks(conn) == []


def test_duplicate_name_rejected(conn):
    import_wordbook(conn, "cet6", VALID_WORDS)
    with pytest.raises(WordbookError):
        import_wordbook(conn, "cet6", VALID_WORDS)
    assert len(list_wordbooks(conn)) == 1


def test_invalid_mode_rejected(conn):
    with pytest.raises(WordbookError):
        import_wordbook(conn, "cet6", VALID_WORDS, mode="random")


def test_import_from_file(conn, tmp_path):
    path = tmp_path / "gre.json"
    path.write_text(json.dumps(VALID_WORDS, ensure_ascii=False), encoding="utf-8")
    book = import_wordbook_file(conn, path)
    assert book.name == "gre"
    assert book.word_count == 3


def test_import_from_bad_file(conn, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(WordbookError):
        import_wordbook_file(conn, path)


def test_current_wordbook_roundtrip(conn):
    assert get_current(conn) is None
    book = import_wordbook(conn, "cet6", VALID_WORDS)
    set_current(conn, book.id)
    assert get_current(conn) == book.id


def test_set_current_unknown_id_rejected(conn):
    with pytest.raises(WordbookError):
        set_current(conn, 999)


def test_get_words_unknown_id_rejected(conn):
    with pytest.raises(WordbookError):
        get_words(conn, 999)
