"""Tests for ArxivCollector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.arxiv_collector import ArxivCollector
from src.models.source import SourceType
from src.storage.local_store import LocalStore

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")

SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.12345v1</id>
    <title>Test Paper: A Novel Approach</title>
    <summary>We propose a new method for solving problem X.</summary>
    <published>2026-03-10T00:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <category term="cs.AI" />
    <category term="cs.CL" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2603.12346v1</id>
    <title>Another Paper</title>
    <summary>Another abstract.</summary>
    <published>2026-03-09T00:00:00Z</published>
    <author><name>Carol</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
"""

OLD_PAPER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2603.00001v1</id>
    <title>Very Old Paper</title>
    <summary>Old abstract.</summary>
    <published>2025-01-01T00:00:00Z</published>
    <author><name>Old Author</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
"""


@pytest.fixture
def arxiv_collector(store):
    return ArxivCollector(store, {"categories": ["cs.AI"], "max_results_per_category": 10})


class TestArxivCollector:
    def test_source_name(self, arxiv_collector):
        assert arxiv_collector.source_name == "arxiv"

    @pytest.mark.asyncio
    async def test_collect_parses_xml(self, arxiv_collector):
        mock_response = httpx.Response(200, text=SAMPLE_ARXIV_XML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            items = await arxiv_collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert items[0].source_type == SourceType.ARXIV_PAPER
        assert items[0].title == "Test Paper: A Novel Approach"
        assert items[0].id == "arxiv:2603.12345v1"
        assert "Alice Smith" in items[0].authors
        assert "Bob Jones" in items[0].authors
        assert items[0].metadata["primary_category"] == "cs.AI"

    @pytest.mark.asyncio
    async def test_collect_filters_old_papers(self, arxiv_collector):
        mock_response = httpx.Response(200, text=OLD_PAPER_XML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            items = await arxiv_collector.collect(date(2026, 3, 10))

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_collect_handles_http_error(self, arxiv_collector):
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("Connection failed"),
        ):
            items = await arxiv_collector.collect(date(2026, 3, 10))

        assert items == []

    @pytest.mark.asyncio
    async def test_collect_deduplicates(self, arxiv_collector):
        arxiv_collector.config["categories"] = ["cs.AI", "cs.CL"]
        mock_response = httpx.Response(200, text=SAMPLE_ARXIV_XML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await arxiv_collector.collect(date(2026, 3, 10))

        ids = [item.id for item in items]
        assert len(ids) == len(set(ids))

    def test_parse_atom_response(self, arxiv_collector):
        items = arxiv_collector._parse_atom_response(SAMPLE_ARXIV_XML, "cs.AI", date(2026, 3, 8))
        assert len(items) == 2
        assert items[0].url.startswith("https://arxiv.org/abs/")

    def test_parse_invalid_xml(self, arxiv_collector):
        items = arxiv_collector._parse_atom_response("not xml", "cs.AI", date(2026, 3, 8))
        assert items == []
