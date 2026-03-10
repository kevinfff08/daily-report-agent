"""Analyzer for social media discussions (Reddit, Hacker News)."""

from __future__ import annotations

import json

from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.analysis import AnalyzedItem, SocialAnalysis
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore

logger = get_logger("analyzers.social")

BATCH_SIZE = 10


class SocialAnalyzer:
    """Analyzes social media discussions using Claude."""

    def __init__(self, llm: LLMClient, store: LocalStore):
        self.llm = llm
        self.store = store

    async def analyze(self, items: list[SourceItem], start_index: int = 1) -> list[AnalyzedItem]:
        """Analyze social items in batches."""
        results: list[AnalyzedItem] = []
        current_index = start_index

        for batch_start in range(0, len(items), BATCH_SIZE):
            batch = items[batch_start: batch_start + BATCH_SIZE]
            batch_results = self._analyze_batch(batch, current_index)
            results.extend(batch_results)
            current_index += len(batch_results)

        logger.info("Analyzed %d social items", len(results))
        return results

    def _analyze_batch(self, items: list[SourceItem], start_index: int) -> list[AnalyzedItem]:
        """Analyze a batch of social items."""
        items_data = []
        for item in items:
            items_data.append({
                "id": item.id,
                "title": item.title,
                "source": item.source_name,
                "content": item.content_snippet[:1500],
                "url": item.url,
                "score": item.metadata.get("score", 0),
                "num_comments": item.metadata.get("num_comments", 0),
            })

        items_json = json.dumps(items_data, ensure_ascii=False, indent=2)
        response = self.llm.generate_json_with_template(
            "social_analysis",
            {"items": items_json},
            max_tokens=8192,
        )

        if not response or not isinstance(response, list):
            logger.warning("Failed to get social analysis from LLM")
            return self._fallback(items, start_index)

        results: list[AnalyzedItem] = []
        for i, item in enumerate(items):
            analysis_data = next((a for a in response if a.get("id") == item.id), None)
            if analysis_data is None and i < len(response):
                analysis_data = response[i]

            if analysis_data:
                analysis = SocialAnalysis(
                    discussion_core=analysis_data.get("discussion_core", "Analysis pending."),
                    key_viewpoints=analysis_data.get("key_viewpoints", "Analysis pending."),
                    technical_substance=analysis_data.get("technical_substance", ""),
                )
            else:
                analysis = SocialAnalysis(
                    discussion_core=item.title,
                    key_viewpoints="Analysis not available.",
                    technical_substance="",
                )

            results.append(AnalyzedItem(
                index=start_index + i,
                source_item=item,
                source_type=item.source_type,
                category="社区热点",
                analysis=analysis,
            ))

        return results

    def _fallback(self, items: list[SourceItem], start_index: int) -> list[AnalyzedItem]:
        results = []
        for i, item in enumerate(items):
            results.append(AnalyzedItem(
                index=start_index + i,
                source_item=item,
                source_type=item.source_type,
                category="社区热点",
                analysis=SocialAnalysis(
                    discussion_core=item.title,
                    key_viewpoints="LLM analysis unavailable.",
                    technical_substance="",
                ),
            ))
        return results
