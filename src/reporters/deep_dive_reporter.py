"""Stage 2: Deep dive report generator (30-60 min reading)."""

from __future__ import annotations

import json
from datetime import date, datetime

from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.analysis import AnalyzedItem
from src.models.report import DeepAnalysis, DeepDiveReport
from src.storage.local_store import LocalStore

logger = get_logger("reporters.deep_dive")


class DeepDiveReporter:
    """Generates the Stage 2 deep dive report for selected items."""

    def __init__(self, llm: LLMClient, store: LocalStore):
        self.llm = llm
        self.store = store

    async def generate(
        self, target_date: date, selected_indices: list[int], all_items: list[AnalyzedItem]
    ) -> tuple[DeepDiveReport, str]:
        """Generate deep dive report for selected items.

        Returns:
            Tuple of (DeepDiveReport model, markdown string)
        """
        # Find selected items
        selected = [item for item in all_items if item.index in selected_indices]
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
            [f"[{i.index:03d}]" for i in selected],
        )

        # Generate deep analysis for each item
        analyses: list[DeepAnalysis] = []
        markdown_parts: list[str] = [
            f"# 深度分析报告 — {target_date.isoformat()}\n",
            f"> 选中条目: {', '.join(f'[{i:03d}]' for i in selected_indices)}\n",
        ]

        for item in selected:
            analysis, md = self._analyze_single(item)
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

    def _analyze_single(self, item: AnalyzedItem) -> tuple[DeepAnalysis, str]:
        """Generate deep analysis for a single item."""
        logger.info("Deep diving into [%03d] %s", item.index, item.source_item.title)

        # Serialize the original analysis for context
        original_analysis = json.dumps(
            item.analysis.model_dump(mode="json"), ensure_ascii=False, indent=2
        )

        markdown = self.llm.generate_with_template(
            "deep_dive",
            {
                "title": item.source_item.title,
                "source": item.source_item.source_name,
                "url": item.source_item.url,
                "original_analysis": original_analysis,
                "content": item.source_item.content_snippet[:3000],
            },
            max_tokens=8192,
            temperature=0.3,
        )

        # Parse sections from markdown (best-effort)
        analysis = DeepAnalysis(
            index=item.index,
            title=item.source_item.title,
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
