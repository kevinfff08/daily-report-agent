"""Tests for PaperAnalyzer."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.analyzers.paper_analyzer import PaperAnalyzer
from src.models.analysis import AnalyzedItem, PaperAnalysis
from src.models.source import SourceItem, SourceType


def make_paper_items(n: int) -> list[SourceItem]:
    return [
        SourceItem(
            id=f"arxiv:paper{i}",
            source_type=SourceType.ARXIV_PAPER,
            title=f"Paper {i}: Novel Method",
            url=f"https://arxiv.org/abs/paper{i}",
            authors=["Author A", "Author B"],
            published=datetime(2026, 3, 10, tzinfo=timezone.utc),
            content_snippet=f"Abstract for paper {i}.",
            metadata={"categories": ["cs.AI"], "source_name": "arXiv cs.AI"},
        )
        for i in range(n)
    ]


@pytest.fixture
def paper_analyzer(mock_llm, store):
    return PaperAnalyzer(mock_llm, store)


class TestPaperAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_success(self, paper_analyzer, mock_llm):
        items = make_paper_items(2)
        mock_llm.generate_json_with_template.return_value = [
            {
                "id": "arxiv:paper0",
                "problem_definition": "Problem statement for paper 0",
                "method_overview": "Method overview for paper 0",
                "main_results": "Results for paper 0",
                "related_work": "Related to prior work",
                "potential_impact": "High impact",
            },
            {
                "id": "arxiv:paper1",
                "problem_definition": "Problem statement for paper 1",
                "method_overview": "Method overview for paper 1",
                "main_results": "Results for paper 1",
                "related_work": "Related work",
                "potential_impact": "Medium impact",
            },
        ]

        results = await paper_analyzer.analyze(items, start_index=1)

        assert len(results) == 2
        assert results[0].index == 1
        assert results[1].index == 2
        assert results[0].category == "论文"
        assert isinstance(results[0].analysis, PaperAnalysis)
        assert results[0].analysis.problem_definition == "Problem statement for paper 0"

    @pytest.mark.asyncio
    async def test_analyze_llm_failure_fallback(self, paper_analyzer, mock_llm):
        items = make_paper_items(2)
        mock_llm.generate_json_with_template.return_value = None

        results = await paper_analyzer.analyze(items, start_index=1)

        assert len(results) == 2
        assert all(isinstance(r.analysis, PaperAnalysis) for r in results)
        assert "LLM analysis unavailable" in results[0].analysis.method_overview

    @pytest.mark.asyncio
    async def test_analyze_batching(self, paper_analyzer, mock_llm):
        """Test that items are processed in batches."""
        items = make_paper_items(12)
        mock_llm.generate_json_with_template.return_value = None  # Use fallback

        results = await paper_analyzer.analyze(items, start_index=1)

        assert len(results) == 12
        # Should have called LLM twice (8 + 4)
        assert mock_llm.generate_json_with_template.call_count == 2
        # Indices should be sequential
        assert [r.index for r in results] == list(range(1, 13))

    @pytest.mark.asyncio
    async def test_analyze_start_index(self, paper_analyzer, mock_llm):
        items = make_paper_items(2)
        mock_llm.generate_json_with_template.return_value = None

        results = await paper_analyzer.analyze(items, start_index=10)

        assert results[0].index == 10
        assert results[1].index == 11

    def test_fallback_analysis(self, paper_analyzer):
        items = make_paper_items(2)
        results = paper_analyzer._fallback_analysis(items, start_index=5)

        assert len(results) == 2
        assert results[0].index == 5
        assert results[1].index == 6
        assert all(r.source_type == SourceType.ARXIV_PAPER for r in results)
