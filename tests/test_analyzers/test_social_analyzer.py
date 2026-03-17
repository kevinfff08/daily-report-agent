"""Tests for SocialAnalyzer."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.analyzers.social_analyzer import SocialAnalyzer
from src.models.analysis import SocialAnalysis
from src.models.source import SourceItem, SourceType


def make_social_items(n: int) -> list[SourceItem]:
    return [
        SourceItem(
            id=f"hn:{40000000 + i}",
            source_type=SourceType.HACKER_NEWS,
            title=f"Discussion about topic {i}",
            url=f"https://news.ycombinator.com/item?id={40000000 + i}",
            authors=["user"],
            published=datetime(2026, 3, 10, tzinfo=timezone.utc),
            content_snippet=f"Discussion content {i}.",
            metadata={"score": 100, "num_comments": 50, "source_name": "Hacker News"},
        )
        for i in range(n)
    ]


@pytest.fixture
def social_analyzer(mock_llm, store):
    return SocialAnalyzer(mock_llm, store)


class TestSocialAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_success(self, social_analyzer, mock_llm):
        items = make_social_items(2)
        mock_llm.generate_json_with_template.return_value = [
            {
                "id": "hn:40000000",
                "discussion_core": "Core discussion about topic 0",
                "key_viewpoints": "Various viewpoints shared",
                "technical_substance": "Technical details here",
            },
            {
                "id": "hn:40000001",
                "discussion_core": "Core discussion about topic 1",
                "key_viewpoints": "Viewpoints for topic 1",
                "technical_substance": "Tech substance 1",
            },
        ]

        results = await social_analyzer.analyze(items, start_index=20)

        assert len(results) == 2
        assert results[0].index == 20
        assert results[0].category == "社区热点"
        assert isinstance(results[0].analysis, SocialAnalysis)

    @pytest.mark.asyncio
    async def test_analyze_llm_failure(self, social_analyzer, mock_llm):
        items = make_social_items(3)
        mock_llm.generate_json_with_template.return_value = None

        results = await social_analyzer.analyze(items, start_index=1)

        assert len(results) == 3
        assert all(isinstance(r.analysis, SocialAnalysis) for r in results)
        assert "LLM analysis unavailable" in results[0].analysis.key_viewpoints

    @pytest.mark.asyncio
    async def test_analyze_batching(self, social_analyzer, mock_llm):
        items = make_social_items(15)
        mock_llm.generate_json_with_template.return_value = None

        results = await social_analyzer.analyze(items, start_index=1)

        assert len(results) == 15
        # BATCH_SIZE = 10, so 2 calls (10 + 5)
        assert mock_llm.generate_json_with_template.call_count == 2
