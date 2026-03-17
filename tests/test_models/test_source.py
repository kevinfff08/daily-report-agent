"""Tests for source data models."""

from datetime import datetime, timezone

from src.models.source import SourceItem, SourceType


class TestSourceType:
    def test_values(self):
        assert SourceType.ARXIV_PAPER == "arxiv_paper"
        assert SourceType.HACKER_NEWS == "hacker_news"
        assert SourceType.YOUTUBE_VIDEO == "youtube_video"
        assert SourceType.BILIBILI_VIDEO == "bilibili_video"
        assert SourceType.SEMANTIC_SCHOLAR == "semantic_scholar"
        assert SourceType.GITHUB_TRENDING == "github_trending"
        assert SourceType.PRODUCT_HUNT == "product_hunt"
        assert SourceType.TAVILY_SEARCH == "tavily_search"

    def test_string_comparison(self):
        assert SourceType.ARXIV_PAPER == "arxiv_paper"
        assert SourceType("hacker_news") == SourceType.HACKER_NEWS


class TestSourceItem:
    def test_create_minimal(self):
        item = SourceItem(
            id="test:1",
            source_type=SourceType.ARXIV_PAPER,
            title="Test Paper",
            url="https://example.com",
            published=datetime(2026, 3, 10, tzinfo=timezone.utc),
        )
        assert item.id == "test:1"
        assert item.authors == []
        assert item.content_snippet == ""
        assert item.metadata == {}

    def test_create_full(self, sample_arxiv_item):
        assert sample_arxiv_item.id == "arxiv:2603.12345"
        assert sample_arxiv_item.source_type == SourceType.ARXIV_PAPER
        assert len(sample_arxiv_item.authors) == 2
        assert "arxiv_id" in sample_arxiv_item.metadata

    def test_source_name_from_metadata(self, sample_arxiv_item):
        assert sample_arxiv_item.source_name == "arXiv cs.AI"

    def test_source_name_fallback(self):
        item = SourceItem(
            id="test:1",
            source_type=SourceType.GITHUB_TRENDING,
            title="Test",
            url="https://example.com",
            published=datetime.now(tz=timezone.utc),
        )
        assert item.source_name == "github_trending"

    def test_serialization_roundtrip(self, sample_arxiv_item):
        json_str = sample_arxiv_item.model_dump_json()
        restored = SourceItem.model_validate_json(json_str)
        assert restored.id == sample_arxiv_item.id
        assert restored.title == sample_arxiv_item.title
        assert restored.source_type == sample_arxiv_item.source_type

    def test_dict_roundtrip(self, sample_arxiv_item):
        data = sample_arxiv_item.model_dump(mode="json")
        restored = SourceItem.model_validate(data)
        assert restored.id == sample_arxiv_item.id
        assert restored.metadata == sample_arxiv_item.metadata
