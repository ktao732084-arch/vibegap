"""前端持久化数据的 HTML 注入回归锁。"""
from pathlib import Path


def test_word_card_escapes_wordbook_fields_before_inner_html():
    script = (
        Path(__file__).resolve().parent.parent
        / "vibegap" / "ui" / "web" / "panels" / "word_card.js"
    ).read_text(encoding="utf-8")
    assert 'escText(shown)' in script
    assert 'escAttr(transFull)' in script
    assert 'escText(word.usphone)' in script
    assert 'escText(w.error' in script


def test_word_card_counts_commit_before_python_can_show_summary():
    script = (
        Path(__file__).resolve().parent.parent
        / "vibegap" / "ui" / "web" / "panels" / "word_card.js"
    ).read_text(encoding="utf-8")
    increment = script.index("window.shell.state.sessionWords += 1;")
    commit = script.index("api.commit_word(result, typos)")
    assert increment < commit


def test_escape_exits_read_only_modes_before_skipping_normal_word():
    script = (
        Path(__file__).resolve().parent.parent
        / "vibegap" / "ui" / "web" / "panels" / "word_card.js"
    ).read_text(encoding="utf-8")
    handler = script[script.index("handleEscape()") : script.index("startReview()")]
    assert handler.index("isReview()") < handler.index("skip_current_and_escape")
    assert handler.index("isBrowsing()") < handler.index("skip_current_and_escape")
