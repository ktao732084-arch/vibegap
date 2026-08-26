"""AIHOT 新闻拉取与缓存(spec §6)。

拉取失败保留旧缓存并降级为空列表,绝不影响背单词主功能。
fetcher 可注入以便测试;默认实现用 httpx,尊重系统代理。
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from vibegap.config import (
    NEWS_API_URL,
    NEWS_HTTP_TIMEOUT_SEC,
    NEWS_POOL_MAX,
    NEWS_REFRESH_MIN,
    NEWS_USER_AGENT,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    summary: str
    published_at: str


def default_fetcher() -> list[NewsItem]:
    """请求 AIHOT 公开 API。返回体带 UTF-8 BOM,用 utf-8-sig 解码。"""
    import httpx

    resp = httpx.get(
        NEWS_API_URL,
        headers={"User-Agent": NEWS_USER_AGENT},
        timeout=NEWS_HTTP_TIMEOUT_SEC,
        follow_redirects=True,
    )
    resp.raise_for_status()
    payload = json.loads(resp.content.decode("utf-8-sig"))
    return parse_items(payload)


def parse_items(payload: object) -> list[NewsItem]:
    """把 AIHOT 返回体解析成 NewsItem 列表;结构不合预期抛 ValueError。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("unexpected AIHOT payload shape")
    items = []
    for raw in payload["items"]:
        if not isinstance(raw, dict) or not raw.get("title"):
            continue
        items.append(
            NewsItem(
                title=str(raw["title"]),
                url=str(raw.get("url", "")),
                source=str(raw.get("source", "")),
                summary=str(raw.get("summary", "")),
                published_at=str(raw.get("publishedAt", "")),
            )
        )
    return items


class NewsFeed:
    """线程安全的新闻缓存;maybe_refresh 由 ticker 周期调用,后台线程拉取。"""

    def __init__(
        self,
        fetcher: Callable[[], list[NewsItem]] = default_fetcher,
        clock: Callable[[], datetime] = datetime.now,
        refresh_interval: timedelta = timedelta(minutes=NEWS_REFRESH_MIN),
    ) -> None:
        self._fetcher = fetcher
        self._clock = clock
        self._refresh_interval = refresh_interval
        self._lock = threading.Lock()
        self._items: tuple[NewsItem, ...] = ()
        self._last_attempt: datetime | None = None
        self._refreshing = False

    def items(self) -> tuple[NewsItem, ...]:
        """当前缓存(可能为空,UI 据此隐藏轮播条)。"""
        with self._lock:
            return self._items

    def maybe_refresh(self, blocking: bool = False) -> None:
        """缓存过期则触发刷新;默认后台线程执行,不阻塞调用方。"""
        with self._lock:
            if self._refreshing or not self._is_stale():
                return
            self._refreshing = True
            self._last_attempt = self._clock()
        if blocking:
            self._do_refresh()
        else:
            threading.Thread(target=self._do_refresh, daemon=True).start()

    def _is_stale(self) -> bool:
        if self._last_attempt is None:
            return True
        return self._clock() - self._last_attempt >= self._refresh_interval

    def _do_refresh(self) -> None:
        try:
            fetched = tuple(self._fetcher())
            with self._lock:
                self._items = _merge_dedup(fetched, self._items)
            logger.info(
                "newsfeed refreshed: %d fetched, pool %d", len(fetched), len(self._items)
            )
        except Exception as exc:  # noqa: BLE001 - 新闻是附属功能,任何失败都只降级
            logger.warning("newsfeed refresh failed (keeping old cache): %s", exc)
        finally:
            with self._lock:
                self._refreshing = False


def _merge_dedup(
    new_items: tuple[NewsItem, ...], old_items: tuple[NewsItem, ...]
) -> tuple[NewsItem, ...]:
    """新条目排前、按 url/标题去重、累积成本地池(上限 NEWS_POOL_MAX)。"""
    seen: set[str] = set()
    merged: list[NewsItem] = []
    for item in list(new_items) + list(old_items):
        key = item.url or item.title
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= NEWS_POOL_MAX:
            break
    return tuple(merged)
