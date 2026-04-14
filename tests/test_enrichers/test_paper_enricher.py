"""Tests for PaperEnricher."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest

from src.enrichers.paper_enricher import PaperEnricher
from src.models.source import SourceItem, SourceType


@pytest.fixture
def paper_enricher() -> PaperEnricher:
    return PaperEnricher()


@pytest.fixture
def paper_enricher_custom_limit() -> PaperEnricher:
    return PaperEnricher(max_chars=12_345)


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
def s2_item_with_pdf_url() -> SourceItem:
    return SourceItem(
        id="s2:pdf123",
        source_type=SourceType.SEMANTIC_SCHOLAR,
        title="S2 Paper with open access PDF",
        url="https://www.semanticscholar.org/paper/pdf123",
        published=datetime(2026, 3, 10, tzinfo=timezone.utc),
        content_snippet="Abstract.",
        metadata={
            "paper_id": "pdf123",
            "pdf_url": "https://papers.example.com/open-access.pdf",
        },
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
        metadata={"paper_id": "xyz789", "doi": "10.1234/example"},
    )


class TestPaperEnricher:
    def test_get_pdf_url_arxiv(self, paper_enricher: PaperEnricher, arxiv_item: SourceItem) -> None:
        url = paper_enricher._get_pdf_url(arxiv_item)
        assert url == "https://arxiv.org/pdf/2603.12345"

    def test_get_pdf_url_s2_with_arxiv(self, paper_enricher: PaperEnricher, s2_item_with_arxiv: SourceItem) -> None:
        url = paper_enricher._get_pdf_url(s2_item_with_arxiv)
        assert url == "https://arxiv.org/pdf/2603.99999"

    def test_get_pdf_url_s2_with_open_access_pdf(self, paper_enricher: PaperEnricher, s2_item_with_pdf_url: SourceItem) -> None:
        url = paper_enricher._get_pdf_url(s2_item_with_pdf_url)
        assert url == "https://papers.example.com/open-access.pdf"

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
        html = """
        <html>
          <head><meta name="citation_pdf_url" content="/content/paper.pdf"></head>
          <body><p>Publisher landing page</p></body>
        </html>
        """
        response_html = {"kind": "html", "content": html.encode("utf-8"), "url": "https://publisher.example/article"}
        with patch.object(paper_enricher, "_fetch_source", new_callable=AsyncMock, return_value=response_html), \
             patch.object(paper_enricher, "_extract_pdf_text", new_callable=AsyncMock, return_value="Recovered PDF text"):
            result = await paper_enricher.enrich(s2_item_no_pdf)
        assert result == "Recovered PDF text"

    @pytest.mark.asyncio
    async def test_enrich_falls_back_to_landing_page_text(
        self,
        paper_enricher: PaperEnricher,
        s2_item_no_pdf: SourceItem,
    ) -> None:
        html = """
        <html>
          <body>
            <article>
              <h1>Paper landing page</h1>
              <p>This page contains the article full text fallback.</p>
            </article>
          </body>
        </html>
        """
        response_html = {"kind": "html", "content": html.encode("utf-8"), "url": "https://publisher.example/article"}
        with patch.object(paper_enricher, "_fetch_source", new_callable=AsyncMock, return_value=response_html):
            result = await paper_enricher.enrich(s2_item_no_pdf)
        assert "article full text fallback" in result

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

    @pytest.mark.asyncio
    async def test_enrich_uses_configured_max_chars(
        self,
        paper_enricher_custom_limit: PaperEnricher,
        arxiv_item: SourceItem,
    ) -> None:
        long_text = "x" * 100_000
        with patch.object(paper_enricher_custom_limit, "_download_pdf", new_callable=AsyncMock, return_value=b"pdf"), \
             patch.object(paper_enricher_custom_limit, "_extract_text", return_value=long_text):
            result = await paper_enricher_custom_limit.enrich(arxiv_item)
        assert len(result) == 12_345
