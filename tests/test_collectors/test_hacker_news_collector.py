"""Tests for HackerNewsCollector."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.hacker_news_collector import HackerNewsCollector
from src.models.source import SourceItem, SourceType

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")


def make_hn_story_response(story_id, title="Test Story", score=100, url=None, **kwargs):
    return httpx.Response(200, json={
        "id": story_id,
        "type": "story",
        "title": title,
        "url": url or f"https://example.com/{story_id}",
        "by": "testuser",
        "score": score,
        "descendants": 50,
        "time": int(datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc).timestamp()),
        **kwargs,
    }, request=DUMMY_REQUEST)


@pytest.fixture
def hn_collector(store):
    return HackerNewsCollector(store, {
        "min_score": 50,
        "max_items": 5,
        "keywords": ["AI", "LLM"],
    })


class TestHackerNewsCollector:
    def test_source_name(self, hn_collector):
        assert hn_collector.source_name == "hackernews"

    @pytest.mark.asyncio
    async def test_collect_basic(self, hn_collector):
        async def mock_get(url, **kwargs):
            if "topstories" in url:
                return httpx.Response(200, json=[1, 2, 3], request=DUMMY_REQUEST)
            story_id = int(url.split("/")[-1].replace(".json", ""))
            return make_hn_story_response(story_id, title=f"AI Story {story_id}", score=100)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await hn_collector.collect(date(2026, 3, 10))

        assert len(items) == 3
        assert all(item.source_type == SourceType.HACKER_NEWS for item in items)

    @pytest.mark.asyncio
    async def test_collect_filters_by_score(self, hn_collector):
        async def mock_get(url, **kwargs):
            if "topstories" in url:
                return httpx.Response(200, json=[1, 2], request=DUMMY_REQUEST)
            story_id = int(url.split("/")[-1].replace(".json", ""))
            score = 100 if story_id == 1 else 10  # Story 2 below threshold
            return make_hn_story_response(story_id, title="AI news", score=score)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await hn_collector.collect(date(2026, 3, 10))

        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_collect_filters_by_keywords(self, hn_collector):
        async def mock_get(url, **kwargs):
            if "topstories" in url:
                return httpx.Response(200, json=[1, 2], request=DUMMY_REQUEST)
            story_id = int(url.split("/")[-1].replace(".json", ""))
            title = "AI breakthrough" if story_id == 1 else "Cooking recipes"
            return make_hn_story_response(story_id, title=title, score=100)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await hn_collector.collect(date(2026, 3, 10))

        assert len(items) == 1
        assert "AI" in items[0].title

    @pytest.mark.asyncio
    async def test_collect_respects_max_items(self, hn_collector):
        hn_collector.config["max_items"] = 2

        async def mock_get(url, **kwargs):
            if "topstories" in url:
                return httpx.Response(200, json=list(range(1, 20)), request=DUMMY_REQUEST)
            story_id = int(url.split("/")[-1].replace(".json", ""))
            return make_hn_story_response(story_id, title="AI Story", score=100)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await hn_collector.collect(date(2026, 3, 10))

        assert len(items) <= 2

    @pytest.mark.asyncio
    async def test_collect_handles_api_error(self, hn_collector):
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("API error"),
        ):
            items = await hn_collector.collect(date(2026, 3, 10))

        assert items == []

    def test_matches_keywords(self):
        item = SourceItem(
            id="hn:1",
            source_type=SourceType.HACKER_NEWS,
            title="New AI model released",
            url="https://example.com",
            published=datetime.now(tz=timezone.utc),
            content_snippet="",
            metadata={},
        )
        assert HackerNewsCollector._matches_keywords(item, ["ai", "llm"]) is True
        assert HackerNewsCollector._matches_keywords(item, ["cooking"]) is False
