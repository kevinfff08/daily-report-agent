"""Central orchestrator wiring all collectors and reporters."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import yaml

from src.filters import ItemFilter
from src.collectors import (
    ArxivCollector,
    BilibiliCollector,
    GitHubTrendingCollector,
    HackerNewsCollector,
    ProductHuntCollector,
    SemanticScholarCollector,
    TavilyCollector,
    YouTubeCollector,
)
from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.config import SourceConfig
from src.models.report import DailyOverview, DeepDiveReport
from src.models.source import SourceItem
from src.reporters import DeepDiveReporter, OverviewReporter
from src.storage.local_store import LocalStore

logger = get_logger("orchestrator")


class DailyReportOrchestrator:
    """Main workflow engine for the daily report system.

    Pipeline:
        Stage 1: collect → overview report (3 LLM calls, one per category)
        Stage 2: user selects items → deep dive (1 LLM call per selected item)
    """

    def __init__(
        self,
        data_dir: str = "data",
        config_dir: str = "config",
        api_key: str | None = None,
        llm_model: str | None = None,
        base_url: str | None = None,
    ):
        self.store = LocalStore(data_dir)
        self.llm = LLMClient(
            api_key=api_key,
            model=llm_model or "claude-sonnet-4-20250514",
            base_url=base_url,
        )
        self.config = self._load_config(config_dir)

        # Collectors (8 sources)
        self.collectors = {
            "arxiv": ArxivCollector(self.store, self.config.arxiv.model_dump()),
            "hackernews": HackerNewsCollector(self.store, self.config.hackernews.model_dump()),
            "youtube": YouTubeCollector(self.store, self.config.youtube.model_dump()),
            "bilibili": BilibiliCollector(self.store, self.config.bilibili.model_dump()),
            "semantic_scholar": SemanticScholarCollector(self.store, self.config.semantic_scholar.model_dump()),
            "github_trending": GitHubTrendingCollector(self.store, self.config.github_trending.model_dump()),
            "product_hunt": ProductHuntCollector(self.store, self.config.product_hunt.model_dump()),
            "tavily": TavilyCollector(self.store, self.config.tavily.model_dump()),
        }

        # Filter and reporters
        self.item_filter = ItemFilter()
        self.overview_reporter = OverviewReporter(self.llm, self.store)
        self.deep_dive_reporter = DeepDiveReporter(self.llm, self.store)

        logger.info("Orchestrator initialized (model=%s)", self.llm.model)

    def _load_config(self, config_dir: str) -> SourceConfig:
        """Load source configuration from YAML."""
        config_path = Path(config_dir) / "sources.yaml"
        if not config_path.exists():
            logger.warning("Config file not found: %s, using defaults", config_path)
            return SourceConfig()

        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        logger.info("Loaded config from %s", config_path)
        return SourceConfig.model_validate(raw)

    # --- Phase 1: Collect ---

    async def collect(
        self, target_date: date, sources: list[str] | None = None
    ) -> dict[str, list[SourceItem]]:
        """Collect data from all (or specified) sources in parallel."""
        logger.info("=== Phase 1: Collecting data for %s ===", target_date)

        active_collectors = self.collectors
        if sources:
            active_collectors = {k: v for k, v in self.collectors.items() if k in sources}

        # Run collectors concurrently
        tasks = {
            name: collector.collect_and_save(target_date)
            for name, collector in active_collectors.items()
        }

        results: dict[str, list[SourceItem]] = {}
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for name, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                logger.error("Collector %s failed: %s", name, result)
                results[name] = []
            else:
                results[name] = result

        total = sum(len(v) for v in results.values())
        logger.info("Collection complete: %d total items from %d sources", total, len(results))
        return results

    # --- Phase 2: Overview Report (3 LLM calls) ---

    async def generate_overview(self, target_date: date) -> tuple[DailyOverview, str]:
        """Generate Stage 1 overview report: load raw → filter → report."""
        logger.info("=== Phase 2: Generating overview report for %s ===", target_date)

        all_items = self._load_all_raw_items(target_date)
        if not all_items:
            logger.warning("No raw data for %s. Run 'collect' first.", target_date)
            return DailyOverview(date=target_date, summary="No data.", total_items=0), ""

        # Rule-based filtering: dedup, score, rank, top-N
        filtered_items = self.item_filter.filter(all_items)

        return await self.overview_reporter.generate(
            target_date, filtered_items, total_raw_count=len(all_items),
        )

    # --- Phase 3: Deep Dive (1 LLM call per selected item) ---

    async def generate_deep_dive(
        self, target_date: date, item_indices: list[int]
    ) -> tuple[DeepDiveReport, str]:
        """Generate Stage 2 deep dive report for selected items."""
        logger.info("=== Phase 3: Deep dive for %s, items=%s ===", target_date, item_indices)

        # Load the items index saved by overview reporter
        items_index = self.store.load_json(
            f"reports/{target_date.isoformat()}/items_index.json"
        )
        if not items_index:
            logger.warning("No items_index found for %s. Run 'report' first.", target_date)
            return DeepDiveReport(date=target_date, selected_items=item_indices), ""

        return await self.deep_dive_reporter.generate(target_date, item_indices, items_index)

    # --- Full Pipeline ---

    async def run(self, target_date: date) -> Path:
        """Execute full pipeline: collect → overview report."""
        await self.collect(target_date)
        overview, markdown = await self.generate_overview(target_date)
        output_path = Path("output") / target_date.isoformat() / "daily_report.md"
        logger.info("=== Pipeline complete. Report at %s ===", output_path)
        return output_path

    # --- Helpers ---

    def _load_all_raw_items(self, target_date: date) -> list[SourceItem]:
        """Load all raw items from all collectors for a date."""
        all_items: list[SourceItem] = []
        for source_name in self.collectors:
            raw_data = self.store.load_raw_items(target_date, source_name)
            if raw_data:
                for item_data in raw_data:
                    try:
                        all_items.append(SourceItem.model_validate(item_data))
                    except Exception as e:
                        logger.debug("Skipping invalid item: %s", e)
        return all_items

    def get_status(self) -> dict:
        """Get system status information."""
        raw_dates = self.store.list_dates("raw")
        analyzed_dates = self.store.list_dates("analyzed")
        report_dates = self.store.list_dates("reports")

        return {
            "llm_model": self.llm.model,
            "collectors": list(self.collectors.keys()),
            "config": {
                "arxiv_categories": self.config.arxiv.categories,
                "hn_min_score": self.config.hackernews.min_score,
                "youtube_channels": len(self.config.youtube.channels),
                "bilibili_users": len(self.config.bilibili.users),
                "semantic_scholar_topics": self.config.semantic_scholar.topics,
                "github_trending_languages": self.config.github_trending.languages,
                "product_hunt_topics": self.config.product_hunt.topics,
                "tavily_searches": len(self.config.tavily.searches),
            },
            "data": {
                "raw_dates": [d.isoformat() for d in raw_dates],
                "analyzed_dates": [d.isoformat() for d in analyzed_dates],
                "report_dates": [d.isoformat() for d in report_dates],
            },
        }
