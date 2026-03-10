"""Tests for analysis data models."""

from datetime import datetime, timezone

from src.models.analysis import (
    AnalyzedItem,
    IndustryAnalysis,
    PaperAnalysis,
    SocialAnalysis,
)
from src.models.source import SourceItem, SourceType


class TestPaperAnalysis:
    def test_create(self, sample_paper_analysis):
        assert "efficiency" in sample_paper_analysis.problem_definition
        assert sample_paper_analysis.method_overview != ""

    def test_serialization(self, sample_paper_analysis):
        data = sample_paper_analysis.model_dump(mode="json")
        restored = PaperAnalysis.model_validate(data)
        assert restored.problem_definition == sample_paper_analysis.problem_definition


class TestIndustryAnalysis:
    def test_create(self, sample_industry_analysis):
        assert "GPT-5" in sample_industry_analysis.release_summary

    def test_serialization(self, sample_industry_analysis):
        json_str = sample_industry_analysis.model_dump_json()
        restored = IndustryAnalysis.model_validate_json(json_str)
        assert restored.release_summary == sample_industry_analysis.release_summary


class TestSocialAnalysis:
    def test_create(self, sample_social_analysis):
        assert "SOTA" in sample_social_analysis.discussion_core

    def test_serialization(self, sample_social_analysis):
        data = sample_social_analysis.model_dump(mode="json")
        restored = SocialAnalysis.model_validate(data)
        assert restored.discussion_core == sample_social_analysis.discussion_core


class TestAnalyzedItem:
    def test_create_with_paper_analysis(self, sample_analyzed_paper):
        assert sample_analyzed_paper.index == 1
        assert sample_analyzed_paper.category == "论文"
        assert isinstance(sample_analyzed_paper.analysis, PaperAnalysis)

    def test_create_with_industry_analysis(self, sample_analyzed_industry):
        assert sample_analyzed_industry.index == 2
        assert sample_analyzed_industry.category == "业界动态"
        assert isinstance(sample_analyzed_industry.analysis, IndustryAnalysis)

    def test_create_with_social_analysis(self, sample_analyzed_social):
        assert sample_analyzed_social.index == 3
        assert isinstance(sample_analyzed_social.analysis, SocialAnalysis)

    def test_index_label(self, sample_analyzed_paper):
        assert sample_analyzed_paper.index_label == "[001]"

    def test_index_label_large_number(self, sample_arxiv_item, sample_paper_analysis):
        item = AnalyzedItem(
            index=42,
            source_item=sample_arxiv_item,
            source_type=SourceType.ARXIV_PAPER,
            category="论文",
            analysis=sample_paper_analysis,
        )
        assert item.index_label == "[042]"

    def test_serialization_roundtrip(self, sample_analyzed_paper):
        data = sample_analyzed_paper.model_dump(mode="json")
        restored = AnalyzedItem.model_validate(data)
        assert restored.index == sample_analyzed_paper.index
        assert restored.category == sample_analyzed_paper.category
        assert restored.source_item.id == sample_analyzed_paper.source_item.id

    def test_json_roundtrip(self, sample_analyzed_industry):
        json_str = sample_analyzed_industry.model_dump_json()
        restored = AnalyzedItem.model_validate_json(json_str)
        assert restored.index == 2
        assert isinstance(restored.analysis, IndustryAnalysis)
