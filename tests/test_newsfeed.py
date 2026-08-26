"""NewsFeed 缓存与降级单测(fetcher 注入,不碰真网)。"""
from datetime import datetime, timedelta

from vibegap.daemon.newsfeed import NewsFeed, NewsItem, parse_items

import pytest

T0 = datetime(2026, 8, 25, 10, 0, 0)
ITEM = NewsItem(title="t1", url="u1", source="s1", summary="", published_at="")


class FakeClock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def test_parse_items_real_shape():
    payload = {
        "count": 1,
        "items": [
            {
                "title": "标题",
                "url": "https://x",
                "source": "NVIDIA Blog（RSS）",
                "publishedAt": "2026-08-24T15:00:19.000Z",
                "summary": "摘要",
                "score": 63,
            },
            {"no_title": True},
        ],
    }
    items = parse_items(payload)
    assert len(items) == 1
    assert items[0].title == "标题"
    assert items[0].source == "NVIDIA Blog（RSS）"


@pytest.mark.parametrize("bad", [None, [], "x", {"items": "not-list"}])
def test_parse_items_bad_shape_raises(bad):
    with pytest.raises(ValueError):
        parse_items(bad)


def test_refresh_populates_cache():
    feed = NewsFeed(fetcher=lambda: [ITEM], clock=FakeClock())
    assert feed.items() == ()
    feed.maybe_refresh(blocking=True)
    assert feed.items() == (ITEM,)


def test_refresh_respects_interval():
    calls = []
    clock = FakeClock()
    feed = NewsFeed(
        fetcher=lambda: calls.append(1) or [ITEM],
        clock=clock,
        refresh_interval=timedelta(minutes=30),
    )
    feed.maybe_refresh(blocking=True)
    feed.maybe_refresh(blocking=True)  # 间隔未到,不重复拉
    assert len(calls) == 1
    clock.now += timedelta(minutes=31)
    feed.maybe_refresh(blocking=True)
    assert len(calls) == 2


def test_pool_accumulates_and_dedupes_across_refreshes():
    clock = FakeClock()
    batches = [
        [NewsItem("a", "u-a", "s", "", ""), NewsItem("b", "u-b", "s", "", "")],
        [NewsItem("b", "u-b", "s", "", ""), NewsItem("c", "u-c", "s", "", "")],
    ]
    feed = NewsFeed(
        fetcher=lambda: batches.pop(0),
        clock=clock,
        refresh_interval=timedelta(minutes=30),
    )
    feed.maybe_refresh(blocking=True)
    clock.now += timedelta(minutes=31)
    feed.maybe_refresh(blocking=True)
    titles = [n.title for n in feed.items()]
    assert titles == ["b", "c", "a"]  # 新条目在前,旧条目保留,b 不重复


def test_fetch_failure_keeps_old_cache():
    clock = FakeClock()
    state = {"fail": False}

    def fetcher():
        if state["fail"]:
            raise RuntimeError("network down")
        return [ITEM]

    feed = NewsFeed(fetcher=fetcher, clock=clock, refresh_interval=timedelta(minutes=30))
    feed.maybe_refresh(blocking=True)
    assert feed.items() == (ITEM,)
    state["fail"] = True
    clock.now += timedelta(minutes=31)
    feed.maybe_refresh(blocking=True)  # 失败:保留旧缓存,不抛异常
    assert feed.items() == (ITEM,)
