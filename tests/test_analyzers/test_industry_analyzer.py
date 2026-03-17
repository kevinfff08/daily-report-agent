"""Tests for IndustryAnalyzer."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.analyzers.industry_analyzer import IndustryAnalyzer
from src.models.analysis import IndustryAnalysis
from src.models.source import SourceItem, SourceType


def make_industry_items(n: int) -> list[SourceItem]:
    return [
        SourceItem(
            id=f"tavily:blog{i}",
            source_type=SourceType.TAVILY_SEARCH,
            title=f"Company Announcement {i}",
            url=f"https://example.com/blog/{i}",
            authors=["Company"],
            published=datetime(2026, 3, 10, tzinfo=timezone.utc),
            content_snippet=f"We are excited to announce product {i}.",
            metadata={"search_name": "Test Blog", "source_name": "Test Blog"},
        )
        for i in range(n)
    ]


@pytest.fixture
def industry_analyzer(mock_llm, store):
    return IndustryAnalyzer(mock_llm, store)


class TestIndustryAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_success(self, industry_analyzer, mock_llm):
        items = make_industry_items(2)
        mock_llm.generate_json_with_template.return_value = [
            {
                "id": "tavily:blog0",
                "release_summary": "Product 0 released",
                "technical_details": "Uses new architecture",
                "competitive_comparison": "Better than competitors",
                "industry_impact": "Significant",
            },
            {
                "id": "tavily:blog1",
                "release_summary": "Product 1 released",
                "technical_details": "Details here",
                "competitive_comparison": "Comparison here",
                "industry_impact": "Moderate",
            },
        ]

        results = await industry_analyzer.analyze(items, start_index=5)

        assert len(results) == 2
        assert results[0].index == 5
        assert results[0].category == "业界动态"
        assert isinstance(results[0].analysis, IndustryAnalysis)
        assert results[0].analysis.release_summary == "Product 0 released"

    @pytest.mark.asyncio
    async def test_analyze_llm_failure(self, industry_analyzer, mock_llm):
        items = make_industry_items(3)
        mock_llm.generate_json_with_template.return_value = None

        results = await industry_analyzer.analyze(items, start_index=1)

        assert len(results) == 3
        assert all(isinstance(r.analysis, IndustryAnalysis) for r in results)
        assert "LLM analysis unavailable" in results[0].analysis.technical_details

    @pytest.mark.asyncio
    async def test_analyze_sequential_indices(self, industry_analyzer, mock_llm):
        items = make_industry_items(5)
        mock_llm.generate_json_with_template.return_value = None

        results = await industry_analyzer.analyze(items, start_index=10)

        assert [r.index for r in results] == [10, 11, 12, 13, 14]
