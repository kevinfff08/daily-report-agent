"""Tests for WebEnricher."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.enrichers.web_enricher import WebEnricher
from src.models.source import SourceItem, SourceType


@pytest.fixture
def web_enricher() -> WebEnricher:
    return WebEnricher()


@pytest.fixture
def tavily_item() -> SourceItem:
    return SourceItem(
        id="tavily:abc123",
        source_type=SourceType.TAVILY_SEARCH,
        title="OpenAI announces GPT-5",
        url="https://openai.com/blog/gpt-5",
        published=datetime(2026, 3, 10, tzinfo=timezone.utc),
        content_snippet="Short snippet.",
        metadata={"search_name": "OpenAI Blog"},
    )


@pytest.fixture
def hn_item() -> SourceItem:
    return SourceItem(
        id="hn:12345",
        source_type=SourceType.HACKER_NEWS,
        title="Show HN: Cool project",
        url="https://example.com/project",
        published=datetime(2026, 3, 10, tzinfo=timezone.utc),
        content_snippet="",
        metadata={"score": 200},
    )


class TestWebEnricher:
    @pytest.mark.asyncio
    async def test_enrich_no_api_key(self, web_enricher: WebEnricher, tavily_item: SourceItem) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = await web_enricher.enrich(tavily_item)
        assert result == ""

    @pytest.mark.asyncio
    async def test_enrich_extract_only(self, web_enricher: WebEnricher, hn_item: SourceItem) -> None:
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), \
             patch.object(web_enricher, "_extract_page", new_callable=AsyncMock, return_value="Full page content here"):
            result = await web_enricher.enrich(hn_item, supplementary_search=False)
        assert "原文内容" in result
        assert "Full page content here" in result

    @pytest.mark.asyncio
    async def test_enrich_with_search(self, web_enricher: WebEnricher, tavily_item: SourceItem) -> None:
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), \
             patch.object(web_enricher, "_extract_page", new_callable=AsyncMock, return_value="Page content"), \
             patch.object(web_enricher, "_search_related", new_callable=AsyncMock, return_value="Related article"):
            result = await web_enricher.enrich(tavily_item, supplementary_search=True)
        assert "原文内容" in result
        assert "Page content" in result
        assert "相关报道与评测" in result
        assert "Related article" in result

    @pytest.mark.asyncio
    async def test_enrich_extract_fails(self, web_enricher: WebEnricher, tavily_item: SourceItem) -> None:
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), \
             patch.object(web_enricher, "_extract_page", new_callable=AsyncMock, return_value=""), \
             patch.object(web_enricher, "_search_related", new_callable=AsyncMock, return_value="Search result"):
            result = await web_enricher.enrich(tavily_item, supplementary_search=True)
        assert "相关报道与评测" in result
        assert "原文内容" not in result

    @pytest.mark.asyncio
    async def test_enrich_both_fail(self, web_enricher: WebEnricher, tavily_item: SourceItem) -> None:
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), \
             patch.object(web_enricher, "_extract_page", new_callable=AsyncMock, return_value=""), \
             patch.object(web_enricher, "_search_related", new_callable=AsyncMock, return_value=""):
            result = await web_enricher.enrich(tavily_item, supplementary_search=True)
        assert result == ""

    @pytest.mark.asyncio
    async def test_extract_page_success(self, web_enricher: WebEnricher) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{"raw_content": "Full extracted text " * 100}]
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with patch("src.enrichers.web_enricher.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await web_enricher._extract_page("test-key", "https://example.com")
        assert "Full extracted text" in result

    @pytest.mark.asyncio
    async def test_search_related_success(self, web_enricher: WebEnricher) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"title": "Article 1", "url": "https://a.com", "content": "Content 1", "raw_content": None},
                {"title": "Article 2", "url": "https://b.com", "content": "Content 2", "raw_content": "Raw 2"},
            ]
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with patch("src.enrichers.web_enricher.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await web_enricher._search_related("test-key", "test query")
        assert "Article 1" in result
        assert "Article 2" in result
