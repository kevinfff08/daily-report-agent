"""Stage 1: Overview report generator (~15 min reading).

Pipeline: filtered items → 3 LLM calls (one per category) → markdown report.
Each LLM call picks the top ~N most important items and writes rich summaries.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.report import DailyOverview, IndexEntry, ReportSection
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore
from src.utils.markdown_math import normalize_markdown_math

logger = get_logger("reporters.overview")

# Category routing: source_type -> category name
_CATEGORY_MAP: dict[SourceType, str] = {
    SourceType.ARXIV_PAPER: "论文",
    SourceType.SEMANTIC_SCHOLAR: "论文",
    SourceType.TAVILY_SEARCH: "业界动态",
    SourceType.PRODUCT_HUNT: "业界动态",
    SourceType.HACKER_NEWS: "社区热点",
    SourceType.YOUTUBE_VIDEO: "社区热点",
    SourceType.BILIBILI_VIDEO: "社区热点",
    SourceType.GITHUB_TRENDING: "社区热点",
}

# Ordered categories for report
_CATEGORY_ORDER = ["论文", "业界动态", "社区热点"]

# How many items LLM should select per category for the final report
_SELECT_COUNTS: dict[str, int] = {
    "论文": 5,
    "业界动态": 3,
    "社区热点": 3,
}


class OverviewReporter:
    """Generates the Stage 1 daily overview report with 3 LLM calls."""

    def __init__(self, llm: LLMClient, store: LocalStore):
        self.llm = llm
        self.store = store

    async def generate(
        self,
        target_date: date,
        all_items: list[SourceItem],
        total_raw_count: int = 0,
    ) -> tuple[DailyOverview, str]:
        """Generate overview from pre-filtered items.

        Args:
            target_date: Report date.
            all_items: Items already filtered and ranked by ItemFilter.
            total_raw_count: Original count before filtering (for display).

        Returns:
            Tuple of (DailyOverview model, markdown string)
        """
        if not total_raw_count:
            total_raw_count = len(all_items)

        logger.info(
            "Generating overview for %s: %d filtered items (from %d raw)",
            target_date, len(all_items), total_raw_count,
        )

        # Assign sequential indices and group by category
        indexed_items: list[tuple[int, SourceItem]] = []
        for i, item in enumerate(all_items, start=1):
            indexed_items.append((i, item))

        groups: dict[str, list[tuple[int, SourceItem]]] = {}
        for idx, item in indexed_items:
            cat = _CATEGORY_MAP.get(item.source_type, "社区热点")
            groups.setdefault(cat, []).append((idx, item))

        # Build index entries (for persistence and deep-dive lookup)
        index_entries = [
            IndexEntry(
                index=idx,
                category=_CATEGORY_MAP.get(item.source_type, "社区热点"),
                title=item.title,
                source=item.source_name,
                url=item.url,
            )
            for idx, item in indexed_items
        ]

        # Generate one LLM summary per category (3 calls total)
        sections: list[ReportSection] = []
        section_markdowns: list[str] = []

        for cat in _CATEGORY_ORDER:
            cat_items = groups.get(cat, [])
            if not cat_items:
                continue

            select_count = _SELECT_COUNTS.get(cat, 3)
            md = self._generate_category_summary(target_date, cat, cat_items, select_count)
            sections.append(ReportSection(
                category=cat,
                items_markdown=md,
                item_count=len(cat_items),
            ))
            section_markdowns.append(f"## {cat}\n\n{md}")

        # Assemble full report markdown
        report_lines = [
            f"# 每日情报概览 — {target_date.isoformat()}\n",
            f"> 从 **{total_raw_count}** 条原始数据中筛选精选，"
            f"候选 **{len(all_items)}** 条\n",
        ]
        report_lines.extend(section_markdowns)

        # Append full candidate index table for deep-dive reference
        report_lines.append("\n---\n\n## 候选条目索引\n")
        report_lines.append(
            "> 以下为经过规则筛选后的全部候选条目。"
            "如需深度分析，请使用 `deep-dive --items \"编号\"` 命令。\n"
        )
        report_lines.append("| 编号 | 类型 | 标题 | 来源 |")
        report_lines.append("|------|------|------|------|")
        for entry in index_entries:
            title_short = entry.title[:60] + ("..." if len(entry.title) > 60 else "")
            report_lines.append(
                f"| [{entry.index:03d}] | {entry.category} | "
                f"[{title_short}]({entry.url}) | {entry.source} |"
            )

        full_markdown = "\n".join(report_lines)

        overview = DailyOverview(
            date=target_date,
            summary=f"从 {total_raw_count} 条原始数据中精选 {len(all_items)} 条候选。",
            sections=sections,
            item_index=index_entries,
            total_items=len(all_items),
            generation_time=datetime.now(),
        )

        # Save
        self.store.save_model(
            f"reports/{target_date.isoformat()}/overview_model.json", overview
        )
        self.store.save_report(target_date, "overview.md", full_markdown)
        self.store.save_output(target_date, "daily_report.md", full_markdown)

        # Save indexed items for deep-dive lookup
        items_index = [
            {"index": idx, "source_item": item.model_dump(mode="json")}
            for idx, item in indexed_items
        ]
        self.store.save_json(
            f"reports/{target_date.isoformat()}/items_index.json", items_index
        )

        logger.info("Overview report saved (%d items, %d sections)", len(all_items), len(sections))
        return overview, full_markdown

    def _generate_category_summary(
        self,
        target_date: date,
        category: str,
        items: list[tuple[int, SourceItem]],
        select_count: int,
    ) -> str:
        """Generate summary for one category via a single LLM call."""
        # Build concise items JSON for the prompt
        items_data = []
        for idx, item in items:
            entry: dict = {
                "index": idx,
                "title": item.title,
                "url": item.url,
                "source": item.source_name,
            }
            # Add richer content for LLM to work with (500 chars for better summaries)
            snippet = item.content_snippet[:500] if item.content_snippet else ""
            if snippet:
                entry["snippet"] = snippet

            # Add key metadata
            if item.authors:
                entry["authors"] = ", ".join(item.authors[:5])
            meta = item.metadata
            if meta.get("score"):
                entry["score"] = meta["score"]
            if meta.get("stars"):
                entry["stars"] = meta["stars"]
            if meta.get("stars_today"):
                entry["stars_today"] = meta["stars_today"]
            if meta.get("votes_count"):
                entry["votes"] = meta["votes_count"]
            if meta.get("num_comments"):
                entry["comments"] = meta["num_comments"]
            if meta.get("citation_count"):
                entry["citations"] = meta["citation_count"]

            items_data.append(entry)

        items_json = json.dumps(items_data, ensure_ascii=False, indent=2)

        logger.info(
            "Generating %s summary (%d candidates, selecting %d)",
            category, len(items), select_count,
        )

        markdown = self.llm.generate_with_template(
            "overview_report",
            {
                "category": category,
                "date": target_date.isoformat(),
                "item_count": len(items),
                "select_count": select_count,
                "items_json": items_json,
            },
            max_tokens=8192,
            temperature=0.3,
        )

        return normalize_markdown_math(markdown)
