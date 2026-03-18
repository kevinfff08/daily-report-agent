"""Tests for OverviewReporter."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from src.reporters.overview_reporter import OverviewReporter


@pytest.fixture
def overview_reporter(mock_llm, store):
    return OverviewReporter(mock_llm, store)


class TestOverviewReporter:
    @pytest.mark.asyncio
    async def test_generate_report(
        self, overview_reporter, mock_llm, sample_arxiv_item, sample_tavily_item
    ):
        mock_llm.generate_with_template.return_value = "# Daily Report\n\nReport content here."
        items = [sample_arxiv_item, sample_tavily_item]

        overview, markdown = await overview_reporter.generate(date(2026, 3, 10), items)

        assert overview.total_items == 2
        assert overview.date == date(2026, 3, 10)
        assert len(overview.item_index) == 2
        assert overview.item_index[0].category == "论文"
        assert overview.item_index[1].category == "业界动态"
        assert "Daily Report" in markdown

    @pytest.mark.asyncio
    async def test_generate_calls_llm(
        self, overview_reporter, mock_llm, sample_arxiv_item
    ):
        mock_llm.generate_with_template.return_value = "Report content"
        await overview_reporter.generate(date(2026, 3, 10), [sample_arxiv_item])

        mock_llm.generate_with_template.assert_called_once()
        call_args = mock_llm.generate_with_template.call_args
        assert call_args[0][0] == "overview_report"
        assert "date" in call_args[0][1]
        assert "item_count" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_generate_saves_output(
        self, overview_reporter, mock_llm, store, sample_arxiv_item, tmp_path
    ):
        mock_llm.generate_with_template.return_value = "LLM report content"
        await overview_reporter.generate(date(2026, 3, 10), [sample_arxiv_item])

        # Verify report saved in data/reports/
        report_path = store.data_dir / "reports" / "2026-03-10" / "overview.md"
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "LLM report content" in content
