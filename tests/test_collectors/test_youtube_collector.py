"""Tests for YouTubeCollector."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.youtube_collector import YouTubeCollector
from src.models.source import SourceType

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")

SEARCH_RESPONSE = {
    "items": [
        {
            "id": {"videoId": "vid001"},
            "snippet": {
                "title": "GPT-5 Explained",
                "description": "A breakdown of GPT-5.",
                "publishedAt": "2026-03-10T10:00:00Z",
                "channelTitle": "AI Explained",
            },
        },
        {
            "id": {"videoId": "vid002"},
            "snippet": {
                "title": "AI News This Week",
                "description": "Weekly AI roundup.",
                "publishedAt": "2026-03-10T12:00:00Z",
                "channelTitle": "AI Explained",
            },
        },
    ]
}

VIDEOS_RESPONSE = {
    "items": [
        {
            "id": "vid001",
            "statistics": {"viewCount": "50000", "likeCount": "2000"},
            "contentDetails": {"duration": "PT10M30S"},
        },
        {
            "id": "vid002",
            "statistics": {"viewCount": "30000", "likeCount": "1500"},
            "contentDetails": {"duration": "PT15M"},
        },
    ]
}


@pytest.fixture
def youtube_config():
    return {
        "channels": [
            {"name": "AI Explained", "channel_id": "UC123"},
        ],
        "max_results_per_channel": 5,
    }


@pytest.fixture
def youtube_collector(store, youtube_config):
    return YouTubeCollector(store, youtube_config)


class TestYouTubeCollector:
    @pytest.mark.asyncio
    async def test_collect_success(self, youtube_collector):
        search_resp = httpx.Response(200, json=SEARCH_RESPONSE, request=DUMMY_REQUEST)
        videos_resp = httpx.Response(200, json=VIDEOS_RESPONSE, request=DUMMY_REQUEST)

        async def mock_get(url, **kwargs):
            if "search" in url:
                return search_resp
            return videos_resp

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
            with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test-key"}):
                items = await youtube_collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert items[0].source_type == SourceType.YOUTUBE_VIDEO
        assert items[0].title == "GPT-5 Explained"
        assert items[0].metadata["view_count"] == 50000
        assert items[0].id == "youtube:vid001"

    @pytest.mark.asyncio
    async def test_no_api_key(self, youtube_collector):
        with patch.dict("os.environ", {}, clear=True):
            items = await youtube_collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_no_channels(self, store):
        collector = YouTubeCollector(store, {"channels": [], "max_results_per_channel": 5})
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test-key"}):
            items = await collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_api_error(self, youtube_collector):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock,
                    side_effect=httpx.HTTPError("API error")):
            with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test-key"}):
                items = await youtube_collector.collect(date(2026, 3, 10))
        assert items == []
