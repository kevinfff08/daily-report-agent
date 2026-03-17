"""Shared test fixtures for DailyReport tests."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models.analysis import (
    AnalyzedItem,
    IndustryAnalysis,
    PaperAnalysis,
    SocialAnalysis,
)
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Provide a temporary data directory."""
    return tmp_path / "data"


@pytest.fixture
def store(tmp_data_dir: Path) -> LocalStore:
    """Provide a LocalStore backed by a temporary directory."""
    return LocalStore(data_dir=str(tmp_data_dir))


@pytest.fixture
def sample_date() -> date:
    return date(2026, 3, 10)


@pytest.fixture
def sample_arxiv_item() -> SourceItem:
    return SourceItem(
        id="arxiv:2603.12345",
        source_type=SourceType.ARXIV_PAPER,
        title="Attention Is All You Need (Again)",
        url="https://arxiv.org/abs/2603.12345",
        authors=["Alice", "Bob"],
        published=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        content_snippet="We propose a novel transformer architecture that improves upon existing methods.",
        metadata={
            "arxiv_id": "2603.12345",
            "categories": ["cs.AI", "cs.CL"],
            "primary_category": "cs.AI",
            "pdf_url": "https://arxiv.org/pdf/2603.12345",
            "source_name": "arXiv cs.AI",
        },
    )


@pytest.fixture
def sample_hn_item() -> SourceItem:
    return SourceItem(
        id="hn:40001234",
        source_type=SourceType.HACKER_NEWS,
        title="Show HN: Open-source LLM evaluation framework",
        url="https://github.com/example/llm-eval",
        authors=["hacker"],
        published=datetime(2026, 3, 10, 16, 0, tzinfo=timezone.utc),
        content_snippet="",
        metadata={
            "story_id": 40001234,
            "score": 200,
            "num_comments": 85,
            "hn_url": "https://news.ycombinator.com/item?id=40001234",
            "source_name": "Hacker News",
        },
    )


@pytest.fixture
def sample_youtube_item() -> SourceItem:
    return SourceItem(
        id="youtube:dQw4w9WgXcQ",
        source_type=SourceType.YOUTUBE_VIDEO,
        title="GPT-5 Explained in 10 Minutes",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        authors=["AI Explained"],
        published=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
        content_snippet="A detailed breakdown of GPT-5's architecture and capabilities.",
        metadata={
            "video_id": "dQw4w9WgXcQ",
            "channel_name": "AI Explained",
            "channel_id": "UCNJ1Ymd5yFuUPtn21xtRZQ",
            "view_count": 50000,
            "source_name": "AI Explained",
        },
    )


@pytest.fixture
def sample_bilibili_item() -> SourceItem:
    return SourceItem(
        id="bilibili:BV1xx411c7mu",
        source_type=SourceType.BILIBILI_VIDEO,
        title="AI Agent Development Guide",
        url="https://www.bilibili.com/video/BV1xx411c7mu",
        authors=["AI UP"],
        published=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
        content_snippet="Complete guide to building AI agents.",
        metadata={
            "bvid": "BV1xx411c7mu",
            "uid": 123456,
            "up_name": "AI UP",
            "play_count": 10000,
            "source_name": "AI UP",
        },
    )


@pytest.fixture
def sample_semantic_scholar_item() -> SourceItem:
    return SourceItem(
        id="s2:abc123def456",
        source_type=SourceType.SEMANTIC_SCHOLAR,
        title="Scaling Laws for Neural Language Models",
        url="https://www.semanticscholar.org/paper/abc123def456",
        authors=["Researcher A", "Researcher B"],
        published=datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc),
        content_snippet="We study empirical scaling laws for language model performance.",
        metadata={
            "paper_id": "abc123def456",
            "citation_count": 150,
            "source_name": "Semantic Scholar",
        },
    )


@pytest.fixture
def sample_github_trending_item() -> SourceItem:
    return SourceItem(
        id="github:owner/cool-ai-project",
        source_type=SourceType.GITHUB_TRENDING,
        title="owner/cool-ai-project",
        url="https://github.com/owner/cool-ai-project",
        authors=["owner"],
        published=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
        content_snippet="An open-source AI framework for building agents.",
        metadata={
            "stars": 5000,
            "language": "Python",
            "stars_today": 200,
            "source_name": "GitHub Trending",
        },
    )


@pytest.fixture
def sample_product_hunt_item() -> SourceItem:
    return SourceItem(
        id="ph:123456",
        source_type=SourceType.PRODUCT_HUNT,
        title="AI Assistant Pro",
        url="https://www.producthunt.com/posts/ai-assistant-pro",
        authors=["Maker"],
        published=datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc),
        content_snippet="The best AI assistant. Your personal AI productivity tool.",
        metadata={
            "post_id": "123456",
            "votes_count": 300,
            "source_name": "Product Hunt",
        },
    )


@pytest.fixture
def sample_tavily_item() -> SourceItem:
    return SourceItem(
        id="tavily:abc123def456",
        source_type=SourceType.TAVILY_SEARCH,
        title="Introducing GPT-5 Turbo",
        url="https://openai.com/blog/gpt-5-turbo",
        authors=[],
        published=datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
        content_snippet="Today we release GPT-5 Turbo, our most capable model yet.",
        metadata={
            "search_name": "OpenAI Blog",
            "search_query": "site:openai.com/blog",
            "score": 0.95,
            "source_name": "OpenAI Blog",
        },
    )


@pytest.fixture
def sample_paper_analysis() -> PaperAnalysis:
    return PaperAnalysis(
        problem_definition="This paper addresses the efficiency problem in transformer models.",
        method_overview="The authors propose a sparse attention mechanism that reduces computation.",
        main_results="Achieves 95% accuracy with 50% less compute on standard benchmarks.",
        related_work="Builds upon prior work in efficient transformers.",
        potential_impact="Could enable larger models on consumer hardware.",
    )


@pytest.fixture
def sample_industry_analysis() -> IndustryAnalysis:
    return IndustryAnalysis(
        release_summary="GPT-5 Turbo released with 2x performance improvement.",
        technical_details="Uses mixture of experts with 8 active experts out of 64 total.",
        competitive_comparison="Outperforms Claude 3 and Gemini on most benchmarks.",
        industry_impact="Raises the bar for commercial LLM capabilities.",
    )


@pytest.fixture
def sample_social_analysis() -> SocialAnalysis:
    return SocialAnalysis(
        discussion_core="Community discusses new SOTA results on ImageNet.",
        key_viewpoints="Some praise efficiency, others question reproducibility.",
        technical_substance="The method uses a novel training schedule.",
    )


@pytest.fixture
def sample_analyzed_paper(sample_arxiv_item, sample_paper_analysis) -> AnalyzedItem:
    return AnalyzedItem(
        index=1,
        source_item=sample_arxiv_item,
        source_type=SourceType.ARXIV_PAPER,
        category="论文",
        analysis=sample_paper_analysis,
    )


@pytest.fixture
def sample_analyzed_industry(sample_tavily_item, sample_industry_analysis) -> AnalyzedItem:
    return AnalyzedItem(
        index=2,
        source_item=sample_tavily_item,
        source_type=SourceType.TAVILY_SEARCH,
        category="业界动态",
        analysis=sample_industry_analysis,
    )


@pytest.fixture
def sample_analyzed_social(sample_hn_item, sample_social_analysis) -> AnalyzedItem:
    return AnalyzedItem(
        index=3,
        source_item=sample_hn_item,
        source_type=SourceType.HACKER_NEWS,
        category="社区热点",
        analysis=sample_social_analysis,
    )


@pytest.fixture
def mock_llm() -> MagicMock:
    """Provide a mock LLMClient."""
    llm = MagicMock()
    llm.model = "test-model"
    return llm
