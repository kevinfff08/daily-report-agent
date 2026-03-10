"""Analyzer for industry news and company announcements."""

from __future__ import annotations

import json

from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.analysis import AnalyzedItem, IndustryAnalysis
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore

logger = get_logger("analyzers.industry")

BATCH_SIZE = 8


class IndustryAnalyzer:
    """Analyzes industry news and announcements using Claude."""

    def __init__(self, llm: LLMClient, store: LocalStore):
        self.llm = llm
        self.store = store

    async def analyze(self, items: list[SourceItem], start_index: int = 1) -> list[AnalyzedItem]:
        """Analyze industry items in batches."""
        results: list[AnalyzedItem] = []
        current_index = start_index

        for batch_start in range(0, len(items), BATCH_SIZE):
            batch = items[batch_start: batch_start + BATCH_SIZE]
            batch_results = self._analyze_batch(batch, current_index)
            results.extend(batch_results)
            current_index += len(batch_results)

        logger.info("Analyzed %d industry items", len(results))
        return results

    def _analyze_batch(self, items: list[SourceItem], start_index: int) -> list[AnalyzedItem]:
        """Analyze a batch of industry items."""
        items_data = []
        for item in items:
            items_data.append({
                "id": item.id,
                "title": item.title,
                "source": item.source_name,
                "content": item.content_snippet[:2000],
                "url": item.url,
            })

        items_json = json.dumps(items_data, ensure_ascii=False, indent=2)
        response = self.llm.generate_json_with_template(
            "industry_analysis",
            {"items": items_json},
            max_tokens=8192,
        )

        if not response or not isinstance(response, list):
            logger.warning("Failed to get industry analysis from LLM")
            return self._fallback(items, start_index)

        results: list[AnalyzedItem] = []
        for i, item in enumerate(items):
            analysis_data = next((a for a in response if a.get("id") == item.id), None)
            if analysis_data is None and i < len(response):
                analysis_data = response[i]

            if analysis_data:
                analysis = IndustryAnalysis(
                    release_summary=analysis_data.get("release_summary", "Analysis pending."),
                    technical_details=analysis_data.get("technical_details", "Analysis pending."),
                    competitive_comparison=analysis_data.get("competitive_comparison", ""),
                    industry_impact=analysis_data.get("industry_impact", ""),
                )
            else:
                analysis = IndustryAnalysis(
                    release_summary=item.content_snippet[:200] or "No content available.",
                    technical_details="Analysis not available.",
                    competitive_comparison="",
                    industry_impact="",
                )

            results.append(AnalyzedItem(
                index=start_index + i,
                source_item=item,
                source_type=item.source_type,
                category="业界动态",
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
                category="业界动态",
                analysis=IndustryAnalysis(
                    release_summary=item.content_snippet[:300] or "No content.",
                    technical_details="LLM analysis unavailable.",
                    competitive_comparison="",
                    industry_impact="",
                ),
            ))
        return results
