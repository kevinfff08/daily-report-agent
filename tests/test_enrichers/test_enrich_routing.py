"""Tests for the enrich_item routing function."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.enrichers import enrich_item
from src.models.source import SourceItem, SourceType


def _make_item(source_type: SourceType) -> SourceItem:
    return SourceItem(
        id=f"test:{source_type.value}",
        source_type=source_type,
        title="Test Item",
        url="https://example.com",
        published=datetime(2026, 3, 10, tzinfo=timezone.utc),
        content_snippet="Original snippet.",
        metadata={"pdf_url": "https://arxiv.org/pdf/test"} if "arxiv" in source_type.value else {},
    )


class TestEnrichRouting:
    @pytest.mark.asyncio
    async def test_arxiv_routes_to_paper(self) -> None:
        item = _make_item(SourceType.ARXIV_PAPER)
        with patch("src.enrichers._paper_enricher.enrich", new_callable=AsyncMock, return_value="PDF text"):
            result = await enrich_item(item)
        assert result == "PDF text"

    @pytest.mark.asyncio
    async def test_semantic_scholar_routes_to_paper(self) -> None:
        item = _make_item(SourceType.SEMANTIC_SCHOLAR)
        with patch("src.enrichers._paper_enricher.enrich", new_callable=AsyncMock, return_value="S2 text"):
            result = await enrich_item(item)
        assert result == "S2 text"

    @pytest.mark.asyncio
    async def test_tavily_routes_to_web_with_search(self) -> None:
        item = _make_item(SourceType.TAVILY_SEARCH)
        with patch("src.enrichers._web_enricher.enrich", new_callable=AsyncMock, return_value="Web content") as mock:
            result = await enrich_item(item)
            mock.assert_called_once_with(item, supplementary_search=True)
        assert result == "Web content"

    @pytest.mark.asyncio
    async def test_product_hunt_routes_to_web_with_search(self) -> None:
        item = _make_item(SourceType.PRODUCT_HUNT)
        with patch("src.enrichers._web_enricher.enrich", new_callable=AsyncMock, return_value="PH content") as mock:
            result = await enrich_item(item)
            mock.assert_called_once_with(item, supplementary_search=True)
        assert result == "PH content"

    @pytest.mark.asyncio
    async def test_hn_routes_to_web_extract_only(self) -> None:
        item = _make_item(SourceType.HACKER_NEWS)
        with patch("src.enrichers._web_enricher.enrich", new_callable=AsyncMock, return_value="HN content") as mock:
            result = await enrich_item(item)
            mock.assert_called_once_with(item, supplementary_search=False)
        assert result == "HN content"

    @pytest.mark.asyncio
    async def test_github_routes_to_web_extract_only(self) -> None:
        item = _make_item(SourceType.GITHUB_TRENDING)
        with patch("src.enrichers._web_enricher.enrich", new_callable=AsyncMock, return_value="GH content") as mock:
            result = await enrich_item(item)
            mock.assert_called_once_with(item, supplementary_search=False)
        assert result == "GH content"

    @pytest.mark.asyncio
    async def test_youtube_falls_back_to_snippet(self) -> None:
        item = _make_item(SourceType.YOUTUBE_VIDEO)
        result = await enrich_item(item)
        assert result == "Original snippet."

    @pytest.mark.asyncio
    async def test_bilibili_falls_back_to_snippet(self) -> None:
        item = _make_item(SourceType.BILIBILI_VIDEO)
        result = await enrich_item(item)
        assert result == "Original snippet."

    @pytest.mark.asyncio
    async def test_paper_enricher_failure_falls_back(self) -> None:
        item = _make_item(SourceType.ARXIV_PAPER)
        with patch("src.enrichers._paper_enricher.enrich", new_callable=AsyncMock, return_value=""):
            result = await enrich_item(item)
        assert result == "Original snippet."

    @pytest.mark.asyncio
    async def test_web_enricher_failure_falls_back(self) -> None:
        item = _make_item(SourceType.TAVILY_SEARCH)
        with patch("src.enrichers._web_enricher.enrich", new_callable=AsyncMock, return_value=""):
            result = await enrich_item(item)
        assert result == "Original snippet."
