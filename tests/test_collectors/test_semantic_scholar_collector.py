"""Tests for SemanticScholarCollector."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.semantic_scholar_collector import SemanticScholarCollector
from src.models.source import SourceType

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")

SEARCH_RESPONSE = {
    "data": [
        {
            "paperId": "abc123",
            "title": "Scaling Laws for Neural Language Models",
            "abstract": "We study empirical scaling laws.",
            "authors": [{"name": "Author A"}, {"name": "Author B"}],
            "year": 2026,
            "publicationDate": "2026-03-08",
            "citationCount": 150,
            "url": "https://www.semanticscholar.org/paper/abc123",
            "externalIds": {"ArXiv": "2603.99999", "DOI": "10.1234/test"},
            "openAccessPdf": {"url": "https://pdf.host/test.pdf"},
            "isOpenAccess": True,
        },
        {
            "paperId": "def456",
            "title": "Efficient Attention Mechanisms",
            "abstract": "We propose a new attention mechanism.",
            "authors": [{"name": "Author C"}],
            "year": 2026,
            "publicationDate": "2026-03-09",
            "citationCount": 50,
            "url": "https://www.semanticscholar.org/paper/def456",
            "externalIds": {},
            "openAccessPdf": None,
            "isOpenAccess": False,
        },
    ]
}


@pytest.fixture
def s2_config():
    return {
        "topics": ["large language models"],
        "max_results": 50,
    }


@pytest.fixture
def s2_collector(store, s2_config):
    return SemanticScholarCollector(store, s2_config)


class TestSemanticScholarCollector:
    @pytest.mark.asyncio
    async def test_collect_success(self, s2_collector):
        resp = httpx.Response(200, json=SEARCH_RESPONSE, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await s2_collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert items[0].source_type == SourceType.SEMANTIC_SCHOLAR
        assert items[0].id == "s2:abc123"
        assert items[0].metadata["citation_count"] == 150
        assert items[0].metadata["arxiv_id"] == "2603.99999"
        assert items[0].metadata["pdf_url"] == "https://pdf.host/test.pdf"
        assert items[0].metadata["is_open_access"] is True

    @pytest.mark.asyncio
    async def test_no_topics(self, store):
        collector = SemanticScholarCollector(store, {"topics": []})
        items = await collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_api_error(self, s2_collector):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock,
                    side_effect=httpx.HTTPError("API error")):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await s2_collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_dedup_across_topics(self, store):
        collector = SemanticScholarCollector(store, {
            "topics": ["topic1", "topic2"],
            "max_results": 50,
        })
        resp = httpx.Response(200, json=SEARCH_RESPONSE, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await collector.collect(date(2026, 3, 10))

        # Same papers returned for both topics, should be deduped
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_date_filtering(self, s2_collector):
        old_response = {
            "data": [
                {
                    "paperId": "old123",
                    "title": "Old Paper",
                    "abstract": "Old abstract.",
                    "authors": [],
                    "year": 2025,
                    "publicationDate": "2025-01-01",
                    "citationCount": 10,
                    "url": "https://www.semanticscholar.org/paper/old123",
                    "externalIds": {},
                },
            ]
        }
        resp = httpx.Response(200, json=old_response, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await s2_collector.collect(date(2026, 3, 10))

        assert len(items) == 0  # Old paper filtered out
