"""Tests for RedditCollector."""

import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.reddit_collector import RedditCollector
from src.models.source import SourceType

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")

SAMPLE_REDDIT_JSON = {
    "data": {
        "children": [
            {
                "data": {
                    "id": "abc123",
                    "title": "[D] New SOTA on ImageNet",
                    "selftext": "This paper achieves SOTA with minimal compute.",
                    "created_utc": datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc).timestamp(),
                    "permalink": "/r/MachineLearning/comments/abc123/",
                    "url": "https://arxiv.org/abs/123",
                    "score": 500,
                    "num_comments": 120,
                    "author": "ml_researcher",
                }
            },
            {
                "data": {
                    "id": "old_post",
                    "title": "Old post",
                    "selftext": "",
                    "created_utc": datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp(),
                    "permalink": "/r/MachineLearning/comments/old_post/",
                    "url": "",
                    "score": 10,
                    "num_comments": 2,
                    "author": "user2",
                }
            },
        ]
    }
}


@pytest.fixture
def reddit_collector(store):
    return RedditCollector(store, {
        "subreddits": ["MachineLearning"],
        "sort": "hot",
        "limit": 25,
    })


class TestRedditCollector:
    def test_source_name(self, reddit_collector):
        assert reddit_collector.source_name == "reddit"

    @pytest.mark.asyncio
    async def test_collect_parses_json(self, reddit_collector):
        mock_response = httpx.Response(200, json=SAMPLE_REDDIT_JSON, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            items = await reddit_collector.collect(date(2026, 3, 10))

        # Old post should be filtered out
        assert len(items) == 1
        assert items[0].source_type == SourceType.REDDIT_POST
        assert items[0].title == "[D] New SOTA on ImageNet"
        assert items[0].metadata["score"] == 500
        assert items[0].metadata["subreddit"] == "MachineLearning"
        assert "ml_researcher" in items[0].authors

    @pytest.mark.asyncio
    async def test_collect_handles_http_error(self, reddit_collector):
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("429"),
        ):
            items = await reddit_collector.collect(date(2026, 3, 10))

        assert items == []

    @pytest.mark.asyncio
    async def test_collect_empty_response(self, reddit_collector):
        mock_response = httpx.Response(200, json={"data": {"children": []}}, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            items = await reddit_collector.collect(date(2026, 3, 10))

        assert items == []
