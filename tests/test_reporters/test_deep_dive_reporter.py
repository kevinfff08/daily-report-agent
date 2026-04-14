"""Tests for DeepDiveReporter."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.report import DeepDiveReport, DeepSection
from src.reporters.deep_dive_reporter import DeepDiveReporter


@pytest.fixture
def deep_dive_reporter(mock_llm, store):
    return DeepDiveReporter(mock_llm, store)


@pytest.fixture
def deep_dive_reporter_configured(mock_llm, store):
    return DeepDiveReporter(
        mock_llm,
        store,
        deep_dive_max_tokens=12_000,
        paper_max_chars=120_000,
    )


def _to_items_index(analyzed_item) -> list[dict]:
    """Convert an AnalyzedItem fixture to the items_index format used by generate()."""
    return [
        {"index": analyzed_item.index, "source_item": analyzed_item.source_item.model_dump(mode="json")}
    ]


# Mock LLM responses for each template type
_PAPER_RESPONSE = (
    "## 研究背景与动机\nBackground text based on full paper.\n"
    "## 技术方法详解\nDetailed technical method.\n"
    "## 实验与结果分析\nExperiment results with numbers.\n"
    "## 局限性与开放问题\nLimitations noted.\n"
    "## 对研究社区的影响\nCommunity impact.\n"
    "## 参考资料\n- [1] Reference one\n- [2] Reference two\n"
)

_INDUSTRY_RESPONSE = (
    "## 产品/技术概述\nProduct overview.\n"
    "## 核心技术架构与实现\nTech architecture.\n"
    "## 竞争格局分析\nCompetitive landscape.\n"
    "## 应用场景与价值\nUse cases.\n"
    "## 发展前景评估\nOutlook.\n"
    "## 信息来源\n- https://example.com\n"
)

_SOCIAL_RESPONSE = (
    "## 事件/项目概述\nProject overview.\n"
    "## 技术实质分析\nTechnical substance.\n"
    "## 社区反响与观点\nCommunity reactions.\n"
    "## 实际应用价值\nPractical value.\n"
    "## 趋势展望\nTrend outlook.\n"
    "## 相关链接\n- https://github.com/example\n"
)


class TestDeepDiveReporter:
    @pytest.mark.asyncio
    async def test_generate_no_matching_items(
        self, deep_dive_reporter, sample_analyzed_paper
    ):
        report, markdown = await deep_dive_reporter.generate(
            date(2026, 3, 10), [999], _to_items_index(sample_analyzed_paper)
        )
        assert isinstance(report, DeepDiveReport)
        assert report.analyses == []
        assert markdown == ""

    @pytest.mark.asyncio
    async def test_generate_paper_item(
        self, deep_dive_reporter, mock_llm, sample_analyzed_paper
    ):
        mock_llm.generate_with_template.return_value = _PAPER_RESPONSE

        with patch("src.reporters.deep_dive_reporter.enrich_item", new_callable=AsyncMock, return_value="Full paper text"):
            report, markdown = await deep_dive_reporter.generate(
                date(2026, 3, 10), [1], _to_items_index(sample_analyzed_paper)
            )

        assert len(report.analyses) == 1
        analysis = report.analyses[0]
        assert analysis.index == 1
        assert analysis.title == sample_analyzed_paper.source_item.title
        assert analysis.source_type == "arxiv_paper"
        assert len(analysis.sections) >= 4
        assert analysis.sections[0].heading == "研究背景与动机"
        assert "Background text" in analysis.sections[0].content
        assert len(analysis.references) == 2

        # Verify paper template was used
        call_args = mock_llm.generate_with_template.call_args
        assert call_args[0][0] == "deep_dive_paper"
        assert "Full paper text" in call_args[0][1]["content"]

    @pytest.mark.asyncio
    async def test_generate_industry_item(
        self, deep_dive_reporter, mock_llm, sample_analyzed_industry
    ):
        mock_llm.generate_with_template.return_value = _INDUSTRY_RESPONSE

        with patch("src.reporters.deep_dive_reporter.enrich_item", new_callable=AsyncMock, return_value="Web content"):
            report, markdown = await deep_dive_reporter.generate(
                date(2026, 3, 10), [2], _to_items_index(sample_analyzed_industry)
            )

        assert len(report.analyses) == 1
        analysis = report.analyses[0]
        assert analysis.source_type == "tavily_search"
        assert analysis.sections[0].heading == "产品/技术概述"

        # Verify industry template was used
        call_args = mock_llm.generate_with_template.call_args
        assert call_args[0][0] == "deep_dive_industry"

    @pytest.mark.asyncio
    async def test_generate_social_item(
        self, deep_dive_reporter, mock_llm, sample_analyzed_social
    ):
        mock_llm.generate_with_template.return_value = _SOCIAL_RESPONSE

        with patch("src.reporters.deep_dive_reporter.enrich_item", new_callable=AsyncMock, return_value="Page content"):
            report, markdown = await deep_dive_reporter.generate(
                date(2026, 3, 10), [3], _to_items_index(sample_analyzed_social)
            )

        assert len(report.analyses) == 1
        analysis = report.analyses[0]
        assert analysis.source_type == "hacker_news"
        assert analysis.sections[0].heading == "事件/项目概述"

        # Verify social template was used
        call_args = mock_llm.generate_with_template.call_args
        assert call_args[0][0] == "deep_dive_social"

    @pytest.mark.asyncio
    async def test_generate_saves_output(
        self, deep_dive_reporter, mock_llm, store, sample_analyzed_paper
    ):
        mock_llm.generate_with_template.return_value = _PAPER_RESPONSE

        with patch("src.reporters.deep_dive_reporter.enrich_item", new_callable=AsyncMock, return_value="text"):
            await deep_dive_reporter.generate(
                date(2026, 3, 10), [1], _to_items_index(sample_analyzed_paper)
            )

        report_path = store.data_dir / "reports" / "2026-03-10" / "deep_dive.md"
        assert report_path.exists()

    @pytest.mark.asyncio
    async def test_generate_uses_configured_limits(
        self,
        deep_dive_reporter_configured,
        mock_llm,
        sample_analyzed_paper,
    ):
        mock_llm.generate_with_template.return_value = _PAPER_RESPONSE

        with patch(
            "src.reporters.deep_dive_reporter.enrich_item",
            new_callable=AsyncMock,
            return_value="Full paper text",
        ) as mock_enrich:
            await deep_dive_reporter_configured.generate(
                date(2026, 3, 10), [1], _to_items_index(sample_analyzed_paper)
            )

        mock_enrich.assert_called_once_with(
            sample_analyzed_paper.source_item,
            paper_max_chars=120_000,
        )
        call_args = mock_llm.generate_with_template.call_args
        assert call_args.kwargs["max_tokens"] == 12_000

    def test_select_template_paper(self):
        from src.models.source import SourceType
        name, headings = DeepDiveReporter._select_template(SourceType.ARXIV_PAPER)
        assert name == "deep_dive_paper"
        assert "研究背景与动机" in headings

    def test_select_template_industry(self):
        from src.models.source import SourceType
        name, headings = DeepDiveReporter._select_template(SourceType.TAVILY_SEARCH)
        assert name == "deep_dive_industry"
        assert "产品/技术概述" in headings

    def test_select_template_social(self):
        from src.models.source import SourceType
        name, headings = DeepDiveReporter._select_template(SourceType.HACKER_NEWS)
        assert name == "deep_dive_social"
        assert "事件/项目概述" in headings

    def test_parse_sections(self):
        md = """## 研究背景与动机
Background content here.
More background.
## 技术方法详解
Technical method details.
## 实验与结果分析
Experiment analysis.
"""
        headings = ["研究背景与动机", "技术方法详解", "实验与结果分析"]
        sections = DeepDiveReporter._parse_sections(md, headings)
        assert len(sections) == 3
        assert sections[0].heading == "研究背景与动机"
        assert "Background content here" in sections[0].content
        assert "More background" in sections[0].content
        assert sections[1].heading == "技术方法详解"
        assert "Technical method" in sections[1].content

    def test_parse_sections_missing(self):
        md = "## Some Other Section\nContent."
        headings = ["研究背景与动机", "技术方法详解"]
        sections = DeepDiveReporter._parse_sections(md, headings)
        assert sections == []
