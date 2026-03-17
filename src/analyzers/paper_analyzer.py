"""Analyzer for academic papers (arXiv, conference papers)."""

from __future__ import annotations

import json

from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.analysis import AnalyzedItem, PaperAnalysis
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore

logger = get_logger("analyzers.paper")

BATCH_SIZE = 8


class PaperAnalyzer:
    """Analyzes academic papers using Claude."""

    def __init__(self, llm: LLMClient, store: LocalStore):
        self.llm = llm
        self.store = store

    async def analyze(self, items: list[SourceItem], start_index: int = 1) -> list[AnalyzedItem]:
        """Analyze papers in batches, returning AnalyzedItems with indices."""
        results: list[AnalyzedItem] = []
        current_index = start_index

        for batch_start in range(0, len(items), BATCH_SIZE):
            batch = items[batch_start: batch_start + BATCH_SIZE]
            batch_results = self._analyze_batch(batch, current_index)
            results.extend(batch_results)
            current_index += len(batch_results)

        logger.info("Analyzed %d papers", len(results))
        return results

    def _analyze_batch(self, items: list[SourceItem], start_index: int) -> list[AnalyzedItem]:
        """Analyze a batch of papers in a single LLM call."""
        papers_data = []
        for item in items:
            papers_data.append({
                "id": item.id,
                "title": item.title,
                "authors": ", ".join(item.authors[:5]),
                "abstract": item.content_snippet[:2000],
                "categories": item.metadata.get("categories", []),
                "url": item.url,
            })

        papers_json = json.dumps(papers_data, ensure_ascii=False, indent=2)
        response = self.llm.generate_json_with_template(
            "paper_analysis",
            {"papers": papers_json},
            max_tokens=8192,
        )

        if not response or not isinstance(response, list):
            logger.warning("Failed to get paper analysis from LLM, creating minimal entries")
            return self._fallback_analysis(items, start_index)

        results: list[AnalyzedItem] = []
        for i, item in enumerate(items):
            # Find matching analysis by id
            analysis_data = next((a for a in response if a.get("id") == item.id), None)
            if analysis_data is None and i < len(response):
                analysis_data = response[i]

            if analysis_data:
                paper_analysis = PaperAnalysis(
                    problem_definition=analysis_data.get("problem_definition", "Analysis pending."),
                    method_overview=analysis_data.get("method_overview", "Analysis pending."),
                    main_results=analysis_data.get("main_results", "Analysis pending."),
                    related_work=analysis_data.get("related_work", ""),
                    potential_impact=analysis_data.get("potential_impact", ""),
                )
            else:
                paper_analysis = PaperAnalysis(
                    problem_definition=item.content_snippet[:200] if item.content_snippet else "No abstract available.",
                    method_overview="Analysis not available.",
                    main_results="Analysis not available.",
                    related_work="",
                    potential_impact="",
                )

            results.append(AnalyzedItem(
                index=start_index + i,
                source_item=item,
                source_type=item.source_type,
                category="论文",
                analysis=paper_analysis,
            ))

        return results

    def _fallback_analysis(self, items: list[SourceItem], start_index: int) -> list[AnalyzedItem]:
        """Create minimal analysis when LLM fails."""
        results = []
        for i, item in enumerate(items):
            results.append(AnalyzedItem(
                index=start_index + i,
                source_item=item,
                source_type=item.source_type,
                category="论文",
                analysis=PaperAnalysis(
                    problem_definition=item.content_snippet[:300] if item.content_snippet else "No abstract.",
                    method_overview="LLM analysis unavailable.",
                    main_results="LLM analysis unavailable.",
                    related_work="",
                    potential_impact="",
                ),
            ))
        return results
