"""Tests for TavilyCollector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.tavily_collector import TavilyCollector
from src.models.source import SourceType

DUMMY_REQUEST = httpx.Request("POST", "https://example.com")

SEARCH_RESPONSE = {
    "results": [
        {
            "title": "Introducing GPT-5 Turbo",
            "url": "https://openai.com/blog/gpt-5-turbo",
            "content": "Today we release GPT-5 Turbo, our most capable model.",
            "score": 0.95,
            "published_date": "2026-03-10T08:00:00Z",
        },
        {
            "title": "GPT-5 API Now Available",
            "url": "https://openai.com/blog/gpt-5-api",
            "content": "The GPT-5 API is now available for developers.",
            "score": 0.88,
        },
    ]
}


@pytest.fixture
def tavily_config():
    return {
        "searches": [
            {"name": "OpenAI Blog", "query": "site:openai.com/blog"},
            {"name": "Anthropic News", "query": "site:anthropic.com/news"},
        ],
        "max_results_per_search": 5,
        "search_depth": "basic",
    }


@pytest.fixture
def tavily_collector(store, tavily_config):
    return TavilyCollector(store, tavily_config)


class TestTavilyCollector:
    @pytest.mark.asyncio
    async def test_collect_success(self, tavily_collector):
        resp = httpx.Response(200, json=SEARCH_RESPONSE, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}):
                items = await tavily_collector.collect(date(2026, 3, 10))

        # 2 searches x 2 results, but deduped by URL
        assert len(items) == 2
        assert items[0].source_type == SourceType.TAVILY_SEARCH
        assert items[0].title == "Introducing GPT-5 Turbo"
        assert items[0].metadata["search_name"] == "OpenAI Blog"
        assert items[0].metadata["score"] == 0.95

    @pytest.mark.asyncio
    async def test_no_api_key(self, tavily_collector):
        with patch.dict("os.environ", {}, clear=True):
            items = await tavily_collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_no_searches(self, store):
        collector = TavilyCollector(store, {"searches": []})
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}):
            items = await collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_api_error(self, tavily_collector):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock,
                    side_effect=httpx.HTTPError("Error")):
            with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}):
                items = await tavily_collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_dedup_across_searches(self, tavily_collector):
        """Same URL found in multiple searches should be deduped."""
        resp = httpx.Response(200, json=SEARCH_RESPONSE, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}):
                items = await tavily_collector.collect(date(2026, 3, 10))

        urls = [item.url for item in items]
        assert len(urls) == len(set(urls))
