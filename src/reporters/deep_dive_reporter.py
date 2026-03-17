"""Stage 2: Deep dive report generator (5-10 min reading per item).

Only analyzes the specific items the user selected from the overview.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.report import DeepAnalysis, DeepDiveReport
from src.models.source import SourceItem
from src.storage.local_store import LocalStore

logger = get_logger("reporters.deep_dive")


class DeepDiveReporter:
    """Generates the Stage 2 deep dive report for selected items."""

    def __init__(self, llm: LLMClient, store: LocalStore):
        self.llm = llm
        self.store = store

    async def generate(
        self,
        target_date: date,
        selected_indices: list[int],
        items_index: list[dict],
    ) -> tuple[DeepDiveReport, str]:
        """Generate deep dive report for selected items.

        Args:
            target_date: The date of the report
            selected_indices: User-selected item index numbers
            items_index: The saved items_index.json data (list of {index, source_item})

        Returns:
            Tuple of (DeepDiveReport model, markdown string)
        """
        # Build index lookup
        index_map: dict[int, SourceItem] = {}
        for entry in items_index:
            idx = entry.get("index", 0)
            try:
                index_map[idx] = SourceItem.model_validate(entry["source_item"])
            except Exception as e:
                logger.debug("Skipping invalid index entry %d: %s", idx, e)

        # Find selected items
        selected: list[tuple[int, SourceItem]] = []
        for idx in selected_indices:
            if idx in index_map:
                selected.append((idx, index_map[idx]))
            else:
                logger.warning("Item index [%03d] not found in items_index", idx)

        if not selected:
            logger.warning("No items found for indices: %s", selected_indices)
            return DeepDiveReport(
                date=target_date,
                selected_items=selected_indices,
                analyses=[],
                generation_time=datetime.now(),
            ), ""

        logger.info(
            "Generating deep dive for %d items: %s",
            len(selected),
            [f"[{i:03d}]" for i, _ in selected],
        )

        # Generate deep analysis for each item
        analyses: list[DeepAnalysis] = []
        markdown_parts: list[str] = [
            f"# 深度分析报告 — {target_date.isoformat()}\n",
            f"> 选中条目: {', '.join(f'[{i:03d}]' for i in selected_indices)}\n",
        ]

        for idx, item in selected:
            analysis, md = self._analyze_single(idx, item)
            analyses.append(analysis)
            markdown_parts.append(md)

        report = DeepDiveReport(
            date=target_date,
            selected_items=selected_indices,
            analyses=analyses,
            generation_time=datetime.now(),
        )

        full_markdown = "\n---\n\n".join(markdown_parts)

        # Save
        self.store.save_model(
            f"reports/{target_date.isoformat()}/deep_dive_model.json", report
        )
        self.store.save_report(target_date, "deep_dive.md", full_markdown)
        output_path = self.store.save_output(target_date, "deep_dive_report.md", full_markdown)

        logger.info("Deep dive report saved to %s", output_path)
        return report, full_markdown

    def _analyze_single(self, index: int, item: SourceItem) -> tuple[DeepAnalysis, str]:
        """Generate deep analysis for a single item."""
        logger.info("Deep diving into [%03d] %s", index, item.title)

        markdown = self.llm.generate_with_template(
            "deep_dive",
            {
                "title": item.title,
                "source": item.source_name,
                "url": item.url,
                "original_analysis": "（首次深度分析，无先前分析）",
                "content": item.content_snippet[:3000],
            },
            max_tokens=8192,
            temperature=0.3,
        )

        # Parse sections from markdown (best-effort)
        analysis = DeepAnalysis(
            index=index,
            title=item.title,
            background_and_motivation=self._extract_section(markdown, "研究背景与动机", "技术方法详解"),
            technical_deep_dive=self._extract_section(markdown, "技术方法详解", "实验分析"),
            experimental_analysis=self._extract_section(markdown, "实验分析", "局限性与开放问题"),
            limitations_and_open_questions=self._extract_section(markdown, "局限性与开放问题", "对研究社区的影响"),
            community_impact=self._extract_section(markdown, "对研究社区的影响", "参考资料"),
            references=[],
        )

        return analysis, markdown

    @staticmethod
    def _extract_section(markdown: str, start_heading: str, end_heading: str) -> str:
        """Extract content between two headings."""
        lines = markdown.split("\n")
        capturing = False
        captured: list[str] = []

        for line in lines:
            stripped = line.strip().lstrip("#").strip()
            if start_heading in stripped:
                capturing = True
                continue
            if end_heading in stripped and capturing:
                break
            if capturing:
                captured.append(line)

        return "\n".join(captured).strip() or "Content not available."
