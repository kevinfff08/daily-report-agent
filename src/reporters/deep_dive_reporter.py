"""Stage 2: Deep dive report generator (5-10 min reading per item).

Only analyzes the specific items the user selected from the overview.
Content is enriched before analysis: papers get full PDF text, web items
get full page content and supplementary search results.
"""

from __future__ import annotations

from datetime import date, datetime

from src.enrichers import enrich_item
from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.report import DeepAnalysis, DeepDiveReport, DeepSection
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore

logger = get_logger("reporters.deep_dive")

# Template selection by source type
_PAPER_TYPES = {SourceType.ARXIV_PAPER, SourceType.SEMANTIC_SCHOLAR}
_INDUSTRY_TYPES = {SourceType.TAVILY_SEARCH, SourceType.PRODUCT_HUNT}
# Everything else (HN, YouTube, Bilibili, GitHub) → social template

# Section headings per template (for parsing LLM output)
_PAPER_HEADINGS = [
    "研究背景与动机", "技术方法详解", "实验与结果分析",
    "局限性与开放问题", "对研究社区的影响", "参考资料",
]
_INDUSTRY_HEADINGS = [
    "产品/技术概述", "核心技术架构与实现", "竞争格局分析",
    "应用场景与价值", "发展前景评估", "信息来源",
]
_SOCIAL_HEADINGS = [
    "事件/项目概述", "技术实质分析", "社区反响与观点",
    "实际应用价值", "趋势展望", "相关链接",
]


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
            analysis, md = await self._analyze_single(idx, item)
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

    async def _analyze_single(self, index: int, item: SourceItem) -> tuple[DeepAnalysis, str]:
        """Generate deep analysis for a single item with enriched content."""
        logger.info("Deep diving into [%03d] %s (%s)", index, item.title, item.source_type.value)

        # Enrich content before LLM analysis
        enriched_content = await enrich_item(item)
        logger.info(
            "Enriched content: %d chars for [%03d] %s",
            len(enriched_content), index, item.title,
        )

        # Select template and headings based on source type
        template_name, headings = self._select_template(item.source_type)

        # Build template variables
        variables: dict[str, str] = {
            "title": item.title,
            "source": item.source_name,
            "url": item.url,
            "content": enriched_content,
        }
        # Paper template also includes authors
        if item.source_type in _PAPER_TYPES:
            variables["authors"] = ", ".join(item.authors) if item.authors else "Unknown"

        markdown = self.llm.generate_with_template(
            template_name,
            variables,
            max_tokens=8192,
            temperature=0.3,
        )

        # Parse sections from markdown
        sections = self._parse_sections(markdown, headings)

        # Extract references from the last section
        refs: list[str] = []
        if sections and sections[-1].heading in ("参考资料", "信息来源", "相关链接"):
            ref_section = sections.pop()
            refs = [
                line.strip().lstrip("- ").lstrip("* ")
                for line in ref_section.content.split("\n")
                if line.strip() and line.strip() != "-"
            ]

        analysis = DeepAnalysis(
            index=index,
            title=item.title,
            source_type=item.source_type.value,
            sections=sections,
            references=refs,
        )

        return analysis, markdown

    @staticmethod
    def _select_template(source_type: SourceType) -> tuple[str, list[str]]:
        """Select the appropriate prompt template based on source type."""
        if source_type in _PAPER_TYPES:
            return "deep_dive_paper", _PAPER_HEADINGS
        if source_type in _INDUSTRY_TYPES:
            return "deep_dive_industry", _INDUSTRY_HEADINGS
        return "deep_dive_social", _SOCIAL_HEADINGS

    @staticmethod
    def _parse_sections(markdown: str, headings: list[str]) -> list[DeepSection]:
        """Parse markdown into DeepSection objects based on expected headings."""
        sections: list[DeepSection] = []
        lines = markdown.split("\n")
        current_heading: str | None = None
        current_lines: list[str] = []

        for line in lines:
            # Check if this line is a heading (## or # with matching text)
            stripped = line.strip().lstrip("#").strip()
            matched_heading = None
            for h in headings:
                if h in stripped:
                    matched_heading = h
                    break

            if matched_heading is not None:
                # Save previous section
                if current_heading is not None:
                    sections.append(DeepSection(
                        heading=current_heading,
                        content="\n".join(current_lines).strip(),
                    ))
                current_heading = matched_heading
                current_lines = []
            elif current_heading is not None:
                current_lines.append(line)

        # Save last section
        if current_heading is not None:
            sections.append(DeepSection(
                heading=current_heading,
                content="\n".join(current_lines).strip(),
            ))

        return sections
