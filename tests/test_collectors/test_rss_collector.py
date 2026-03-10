"""Tests for RSSCollector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.rss_collector import RSSCollector
from src.models.source import SourceType
from src.storage.local_store import LocalStore

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <item>
      <title>New AI Release</title>
      <link>https://example.com/post1</link>
      <description>&lt;p&gt;We released a new AI model.&lt;/p&gt;</description>
      <pubDate>Tue, 10 Mar 2026 08:00:00 GMT</pubDate>
      <guid>https://example.com/post1</guid>
    </item>
    <item>
      <title>Old Post</title>
      <link>https://example.com/old</link>
      <description>An old post.</description>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def rss_collector(store):
    config = {
        "feeds": [
            {"name": "Test Blog", "url": "https://example.com/rss", "category": "industry"},
        ],
    }
    return RSSCollector(store, config)


class TestRSSCollector:
    def test_source_name(self, rss_collector):
        assert rss_collector.source_name == "rss"

    @pytest.mark.asyncio
    async def test_collect_parses_rss(self, rss_collector):
        mock_response = httpx.Response(200, text=SAMPLE_RSS_XML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            items = await rss_collector.collect(date(2026, 3, 10))

        # Should filter out old post
        assert len(items) == 1
        assert items[0].title == "New AI Release"
        assert items[0].source_type == SourceType.RSS_ARTICLE
        # HTML should be stripped
        assert "<p>" not in items[0].content_snippet
        assert items[0].metadata["category"] == "industry"

    @pytest.mark.asyncio
    async def test_collect_no_feeds(self, store):
        collector = RSSCollector(store, {"feeds": []})
        items = await collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_collect_handles_http_error(self, rss_collector):
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("Timeout"),
        ):
            items = await rss_collector.collect(date(2026, 3, 10))

        assert items == []

    def test_parse_entry_date_none(self):
        """Test handling of entries with no date."""

        class FakeEntry:
            pass

        result = RSSCollector._parse_entry_date(FakeEntry())
        assert result is None
