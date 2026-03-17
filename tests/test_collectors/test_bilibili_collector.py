"""Tests for BilibiliCollector."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.bilibili_collector import (
    BilibiliCollector,
    _get_mixin_key,
    _sign_params,
)
from src.models.source import SourceType

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")

NAV_RESPONSE = {
    "data": {
        "wbi_img": {
            "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
            "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
        }
    }
}

SEARCH_RESPONSE = {
    "data": {
        "list": {
            "vlist": [
                {
                    "bvid": "BV1xx411c7mu",
                    "aid": 12345,
                    "title": "AI Agent Tutorial",
                    "description": "How to build AI agents.",
                    "created": 1741564800,  # 2025-03-10 in UTC
                    "play": 10000,
                    "comment": 50,
                },
            ]
        }
    }
}


@pytest.fixture
def bilibili_config():
    return {
        "users": [{"name": "AI UP", "uid": 123456}],
        "max_results_per_user": 5,
    }


@pytest.fixture
def bilibili_collector(store, bilibili_config):
    return BilibiliCollector(store, bilibili_config)


class TestWBISigning:
    def test_get_mixin_key(self):
        raw = "7cd084941338484aae1ad9425b84077c4932caff0ff746eab6f01bf08b70ac45"
        key = _get_mixin_key(raw)
        assert len(key) == 32

    def test_sign_params(self):
        params = {"mid": 123456, "ps": 5, "pn": 1, "order": "pubdate"}
        mixin_key = "abcdefghijklmnopqrstuvwxyz012345"
        signed = _sign_params(params, mixin_key)
        assert "w_rid" in signed
        assert "wts" in signed
        assert signed["mid"] == 123456


class TestBilibiliCollector:
    @pytest.mark.asyncio
    async def test_collect_success(self, bilibili_collector):
        nav_resp = httpx.Response(200, json=NAV_RESPONSE, request=DUMMY_REQUEST)
        search_resp = httpx.Response(200, json=SEARCH_RESPONSE, request=DUMMY_REQUEST)

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "nav" in url:
                return nav_resp
            return search_resp

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
            items = await bilibili_collector.collect(date(2025, 3, 10))

        assert len(items) >= 1
        assert items[0].source_type == SourceType.BILIBILI_VIDEO
        assert items[0].id.startswith("bilibili:")

    @pytest.mark.asyncio
    async def test_no_users(self, store):
        collector = BilibiliCollector(store, {"users": []})
        items = await collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_nav_failure(self, bilibili_collector):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock,
                    side_effect=httpx.HTTPError("Nav failed")):
            items = await bilibili_collector.collect(date(2026, 3, 10))
        assert items == []
