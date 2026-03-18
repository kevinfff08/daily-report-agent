"""Tests for PaperEnricher."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.enrichers.paper_enricher import PaperEnricher
from src.models.source import SourceItem, SourceType


@pytest.fixture
def paper_enricher() -> PaperEnricher:
    return PaperEnricher()


@pytest.fixture
def arxiv_item() -> SourceItem:
    return SourceItem(
        id="arxiv:2603.12345",
        source_type=SourceType.ARXIV_PAPER,
        title="Test Paper",
        url="https://arxiv.org/abs/2603.12345",
        published=datetime(2026, 3, 10, tzinfo=timezone.utc),
        content_snippet="Abstract text.",
        metadata={
            "arxiv_id": "2603.12345",
            "pdf_url": "https://arxiv.org/pdf/2603.12345",
        },
    )


@pytest.fixture
def s2_item_with_arxiv() -> SourceItem:
    return SourceItem(
        id="s2:abc123",
        source_type=SourceType.SEMANTIC_SCHOLAR,
        title="S2 Paper with arXiv",
        url="https://www.semanticscholar.org/paper/abc123",
        published=datetime(2026, 3, 10, tzinfo=timezone.utc),
        content_snippet="Abstract.",
        metadata={"paper_id": "abc123", "arxiv_id": "2603.99999"},
    )


@pytest.fixture
def s2_item_no_pdf() -> SourceItem:
    return SourceItem(
        id="s2:xyz789",
        source_type=SourceType.SEMANTIC_SCHOLAR,
        title="S2 Paper no PDF",
        url="https://www.semanticscholar.org/paper/xyz789",
        published=datetime(2026, 3, 10, tzinfo=timezone.utc),
        content_snippet="Abstract.",
        metadata={"paper_id": "xyz789"},
    )


class TestPaperEnricher:
    def test_get_pdf_url_arxiv(self, paper_enricher: PaperEnricher, arxiv_item: SourceItem) -> None:
        url = paper_enricher._get_pdf_url(arxiv_item)
        assert url == "https://arxiv.org/pdf/2603.12345"

    def test_get_pdf_url_s2_with_arxiv(self, paper_enricher: PaperEnricher, s2_item_with_arxiv: SourceItem) -> None:
        url = paper_enricher._get_pdf_url(s2_item_with_arxiv)
        assert url == "https://arxiv.org/pdf/2603.99999"

    def test_get_pdf_url_s2_no_pdf(self, paper_enricher: PaperEnricher, s2_item_no_pdf: SourceItem) -> None:
        url = paper_enricher._get_pdf_url(s2_item_no_pdf)
        assert url == ""

    @pytest.mark.asyncio
    async def test_enrich_success(self, paper_enricher: PaperEnricher, arxiv_item: SourceItem) -> None:
        fake_pdf = b"%PDF-1.4 fake content"
        with patch.object(paper_enricher, "_download_pdf", new_callable=AsyncMock, return_value=fake_pdf), \
             patch.object(paper_enricher, "_extract_text", return_value="Full paper text here " * 100):
            result = await paper_enricher.enrich(arxiv_item)
        assert "Full paper text here" in result

    @pytest.mark.asyncio
    async def test_enrich_download_failure(self, paper_enricher: PaperEnricher, arxiv_item: SourceItem) -> None:
        with patch.object(paper_enricher, "_download_pdf", new_callable=AsyncMock, side_effect=Exception("timeout")):
            result = await paper_enricher.enrich(arxiv_item)
        assert result == ""

    @pytest.mark.asyncio
    async def test_enrich_no_pdf_url(self, paper_enricher: PaperEnricher, s2_item_no_pdf: SourceItem) -> None:
        result = await paper_enricher.enrich(s2_item_no_pdf)
        assert result == ""

    @pytest.mark.asyncio
    async def test_enrich_extract_failure(self, paper_enricher: PaperEnricher, arxiv_item: SourceItem) -> None:
        with patch.object(paper_enricher, "_download_pdf", new_callable=AsyncMock, return_value=b"bad"), \
             patch.object(paper_enricher, "_extract_text", side_effect=Exception("corrupt PDF")):
            result = await paper_enricher.enrich(arxiv_item)
        assert result == ""

    @pytest.mark.asyncio
    async def test_enrich_truncates_long_text(self, paper_enricher: PaperEnricher, arxiv_item: SourceItem) -> None:
        long_text = "x" * 100_000
        with patch.object(paper_enricher, "_download_pdf", new_callable=AsyncMock, return_value=b"pdf"), \
             patch.object(paper_enricher, "_extract_text", return_value=long_text):
            result = await paper_enricher.enrich(arxiv_item)
        assert len(result) == 40_000
