"""Tests for DeepDiveReporter."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from src.models.report import DeepDiveReport
from src.reporters.deep_dive_reporter import DeepDiveReporter


@pytest.fixture
def deep_dive_reporter(mock_llm, store):
    return DeepDiveReporter(mock_llm, store)


class TestDeepDiveReporter:
    @pytest.mark.asyncio
    async def test_generate_no_matching_items(
        self, deep_dive_reporter, sample_analyzed_paper
    ):
        report, markdown = await deep_dive_reporter.generate(
            date(2026, 3, 10), [999], [sample_analyzed_paper]
        )
        assert isinstance(report, DeepDiveReport)
        assert report.analyses == []
        assert markdown == ""

    @pytest.mark.asyncio
    async def test_generate_with_matching_items(
        self, deep_dive_reporter, mock_llm, sample_analyzed_paper
    ):
        mock_llm.generate_with_template.return_value = (
            "## 研究背景与动机\nBackground text.\n"
            "## 技术方法详解\nTechnical details.\n"
            "## 实验分析\nExperiment results.\n"
            "## 局限性与开放问题\nLimitations.\n"
            "## 对研究社区的影响\nImpact.\n"
            "## 参考资料\n- ref1\n"
        )

        report, markdown = await deep_dive_reporter.generate(
            date(2026, 3, 10), [1], [sample_analyzed_paper]
        )

        assert len(report.analyses) == 1
        assert report.analyses[0].index == 1
        assert report.analyses[0].title == sample_analyzed_paper.source_item.title
        assert "Background text" in report.analyses[0].background_and_motivation
        assert markdown != ""

    @pytest.mark.asyncio
    async def test_generate_saves_output(
        self, deep_dive_reporter, mock_llm, store, sample_analyzed_paper
    ):
        mock_llm.generate_with_template.return_value = "## 研究背景与动机\nText\n## 技术方法详解\nTech\n## 实验分析\nExp\n## 局限性与开放问题\nLim\n## 对研究社区的影响\nImpact\n## 参考资料\n"
        await deep_dive_reporter.generate(
            date(2026, 3, 10), [1], [sample_analyzed_paper]
        )

        report_path = store.data_dir / "reports" / "2026-03-10" / "deep_dive.md"
        assert report_path.exists()

    def test_extract_section(self):
        markdown = """## 研究背景与动机
Background content here.
More background.
## 技术方法详解
Technical method details.
## 实验分析
Experiment analysis.
"""
        result = DeepDiveReporter._extract_section(markdown, "研究背景与动机", "技术方法详解")
        assert "Background content here" in result
        assert "More background" in result
        assert "Technical method" not in result

    def test_extract_section_missing(self):
        markdown = "## Some Other Section\nContent."
        result = DeepDiveReporter._extract_section(markdown, "研究背景与动机", "技术方法详解")
        assert result == "Content not available."
