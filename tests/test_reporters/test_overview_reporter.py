"""Tests for OverviewReporter."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from src.models.analysis import AnalyzedItem, PaperAnalysis, IndustryAnalysis
from src.models.source import SourceType
from src.reporters.overview_reporter import OverviewReporter


@pytest.fixture
def overview_reporter(mock_llm, store):
    return OverviewReporter(mock_llm, store)


class TestOverviewReporter:
    @pytest.mark.asyncio
    async def test_generate_report(
        self, overview_reporter, mock_llm, sample_analyzed_paper, sample_analyzed_industry
    ):
        mock_llm.generate_with_template.return_value = "# Daily Report\n\nReport content here."
        items = [sample_analyzed_paper, sample_analyzed_industry]

        overview, markdown = await overview_reporter.generate(date(2026, 3, 10), items)

        assert overview.total_items == 2
        assert overview.date == date(2026, 3, 10)
        assert len(overview.item_index) == 2
        assert overview.item_index[0].category == "论文"
        assert overview.item_index[1].category == "业界动态"
        assert "Daily Report" in markdown

    @pytest.mark.asyncio
    async def test_generate_calls_llm(
        self, overview_reporter, mock_llm, sample_analyzed_paper
    ):
        mock_llm.generate_with_template.return_value = "Report"
        await overview_reporter.generate(date(2026, 3, 10), [sample_analyzed_paper])

        mock_llm.generate_with_template.assert_called_once()
        call_args = mock_llm.generate_with_template.call_args
        assert call_args[0][0] == "overview_report"
        assert "date" in call_args[0][1]
        assert "total_items" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_generate_saves_output(
        self, overview_reporter, mock_llm, store, sample_analyzed_paper, tmp_path
    ):
        mock_llm.generate_with_template.return_value = "# Report"
        await overview_reporter.generate(date(2026, 3, 10), [sample_analyzed_paper])

        # Verify report saved in data/reports/
        report_path = store.data_dir / "reports" / "2026-03-10" / "overview.md"
        assert report_path.exists()
        assert report_path.read_text(encoding="utf-8") == "# Report"

    def test_build_sections(self, overview_reporter, sample_analyzed_paper, sample_analyzed_industry):
        items = [sample_analyzed_paper, sample_analyzed_industry]
        sections = overview_reporter._build_sections(items)

        assert len(sections) == 2
        categories = [s.category for s in sections]
        assert "论文" in categories
        assert "业界动态" in categories

    def test_build_sections_counts(self, overview_reporter, sample_analyzed_paper):
        items = [sample_analyzed_paper]
        sections = overview_reporter._build_sections(items)
        assert sections[0].item_count == 1
