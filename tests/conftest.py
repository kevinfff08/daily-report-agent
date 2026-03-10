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
def sample_rss_item() -> SourceItem:
    return SourceItem(
        id="rss:OpenAI Blog:12345678",
        source_type=SourceType.RSS_ARTICLE,
        title="Introducing GPT-5 Turbo",
        url="https://openai.com/blog/gpt-5-turbo",
        authors=["OpenAI"],
        published=datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
        content_snippet="Today we release GPT-5 Turbo, our most capable model yet.",
        metadata={
            "feed_name": "OpenAI Blog",
            "feed_url": "https://openai.com/blog/rss.xml",
            "category": "industry",
            "source_name": "OpenAI Blog",
        },
    )


@pytest.fixture
def sample_reddit_item() -> SourceItem:
    return SourceItem(
        id="reddit:MachineLearning:abc123",
        source_type=SourceType.REDDIT_POST,
        title="[D] New SOTA on ImageNet with minimal compute",
        url="https://www.reddit.com/r/MachineLearning/comments/abc123/",
        authors=["ml_researcher"],
        published=datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc),
        content_snippet="Interesting new paper achieves SOTA on ImageNet using only 10% of compute.",
        metadata={
            "subreddit": "MachineLearning",
            "score": 500,
            "num_comments": 120,
            "source_name": "r/MachineLearning",
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
def sample_analyzed_industry(sample_rss_item, sample_industry_analysis) -> AnalyzedItem:
    return AnalyzedItem(
        index=2,
        source_item=sample_rss_item,
        source_type=SourceType.RSS_ARTICLE,
        category="业界动态",
        analysis=sample_industry_analysis,
    )


@pytest.fixture
def sample_analyzed_social(sample_reddit_item, sample_social_analysis) -> AnalyzedItem:
    return AnalyzedItem(
        index=3,
        source_item=sample_reddit_item,
        source_type=SourceType.REDDIT_POST,
        category="社区热点",
        analysis=sample_social_analysis,
    )


@pytest.fixture
def mock_llm() -> MagicMock:
    """Provide a mock LLMClient."""
    llm = MagicMock()
    llm.model = "test-model"
    return llm
