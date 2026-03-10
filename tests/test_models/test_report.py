"""Tests for report data models."""

from datetime import date, datetime

from src.models.report import (
    DailyOverview,
    DeepAnalysis,
    DeepDiveReport,
    IndexEntry,
    ReportSection,
)


class TestIndexEntry:
    def test_create(self):
        entry = IndexEntry(
            index=1,
            category="论文",
            title="Test Paper",
            source="arXiv cs.AI",
            url="https://arxiv.org/abs/1234",
        )
        assert entry.index == 1
        assert entry.index_label == "[001]"

    def test_index_label_format(self):
        entry = IndexEntry(index=15, category="", title="", source="", url="")
        assert entry.index_label == "[015]"


class TestReportSection:
    def test_create(self):
        section = ReportSection(
            category="论文",
            items_markdown="## Papers\n- Paper 1\n- Paper 2",
            item_count=2,
        )
        assert section.category == "论文"
        assert section.item_count == 2


class TestDailyOverview:
    def test_create_minimal(self):
        overview = DailyOverview(
            date=date(2026, 3, 10),
            summary="No data.",
            total_items=0,
        )
        assert overview.total_items == 0
        assert overview.sections == []
        assert overview.item_index == []

    def test_create_full(self):
        overview = DailyOverview(
            date=date(2026, 3, 10),
            summary="今日共收录 5 条信息。",
            sections=[
                ReportSection(category="论文", items_markdown="...", item_count=3),
                ReportSection(category="业界动态", items_markdown="...", item_count=2),
            ],
            item_index=[
                IndexEntry(index=1, category="论文", title="Paper 1", source="arXiv", url="url1"),
                IndexEntry(index=2, category="论文", title="Paper 2", source="arXiv", url="url2"),
            ],
            total_items=5,
        )
        assert overview.total_items == 5
        assert len(overview.sections) == 2
        assert len(overview.item_index) == 2

    def test_serialization(self):
        overview = DailyOverview(
            date=date(2026, 3, 10),
            summary="Test",
            total_items=0,
        )
        data = overview.model_dump(mode="json")
        restored = DailyOverview.model_validate(data)
        assert restored.date == overview.date
        assert restored.summary == "Test"


class TestDeepAnalysis:
    def test_create(self):
        analysis = DeepAnalysis(
            index=1,
            title="Test Paper",
            background_and_motivation="Background text here.",
            technical_deep_dive="Technical details here.",
            experimental_analysis="Experimental analysis here.",
            limitations_and_open_questions="Limitations discussed.",
            community_impact="Impact on community.",
            references=["ref1", "ref2"],
        )
        assert analysis.index == 1
        assert len(analysis.references) == 2

    def test_defaults(self):
        analysis = DeepAnalysis(
            index=1,
            title="Test",
            background_and_motivation="",
            technical_deep_dive="",
            experimental_analysis="",
            limitations_and_open_questions="",
            community_impact="",
        )
        assert analysis.references == []


class TestDeepDiveReport:
    def test_create_empty(self):
        report = DeepDiveReport(
            date=date(2026, 3, 10),
            selected_items=[1, 3, 5],
        )
        assert report.selected_items == [1, 3, 5]
        assert report.analyses == []

    def test_serialization(self):
        report = DeepDiveReport(
            date=date(2026, 3, 10),
            selected_items=[1, 2],
            analyses=[
                DeepAnalysis(
                    index=1,
                    title="Paper 1",
                    background_and_motivation="bg",
                    technical_deep_dive="tech",
                    experimental_analysis="exp",
                    limitations_and_open_questions="lim",
                    community_impact="impact",
                ),
            ],
        )
        json_str = report.model_dump_json()
        restored = DeepDiveReport.model_validate_json(json_str)
        assert len(restored.analyses) == 1
        assert restored.analyses[0].title == "Paper 1"
