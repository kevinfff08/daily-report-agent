"""Central orchestrator wiring all collectors, analyzers, and reporters."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import yaml

from src.analyzers import IndustryAnalyzer, PaperAnalyzer, SocialAnalyzer
from src.collectors import (
    ArxivCollector,
    HackerNewsCollector,
    RedditCollector,
    RSSCollector,
)
from src.llm.client import LLMClient
from src.logging_config import get_logger
from src.models.analysis import AnalyzedItem
from src.models.config import SourceConfig
from src.models.report import DailyOverview, DeepDiveReport
from src.models.source import SourceItem, SourceType
from src.reporters import DeepDiveReporter, OverviewReporter
from src.storage.local_store import LocalStore

logger = get_logger("orchestrator")


class DailyReportOrchestrator:
    """Main workflow engine for the daily report system."""

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

        # Collectors
        self.collectors = {
            "arxiv": ArxivCollector(self.store, self.config.arxiv.model_dump()),
            "rss": RSSCollector(self.store, self.config.rss.model_dump()),
            "reddit": RedditCollector(self.store, self.config.reddit.model_dump()),
            "hackernews": HackerNewsCollector(self.store, self.config.hackernews.model_dump()),
        }

        # Analyzers
        self.paper_analyzer = PaperAnalyzer(self.llm, self.store)
        self.industry_analyzer = IndustryAnalyzer(self.llm, self.store)
        self.social_analyzer = SocialAnalyzer(self.llm, self.store)

        # Reporters
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

    # --- Phase 2: Analyze ---

    async def analyze(self, target_date: date) -> list[AnalyzedItem]:
        """Analyze all collected items for a date."""
        logger.info("=== Phase 2: Analyzing data for %s ===", target_date)

        # Load raw data
        all_items: list[SourceItem] = []
        for source_name in self.collectors:
            raw_data = self.store.load_raw_items(target_date, source_name)
            if raw_data:
                for item_data in raw_data:
                    try:
                        all_items.append(SourceItem.model_validate(item_data))
                    except Exception as e:
                        logger.debug("Skipping invalid item: %s", e)

        if not all_items:
            logger.warning("No raw data found for %s", target_date)
            return []

        # Classify items
        papers = [i for i in all_items if i.source_type == SourceType.ARXIV_PAPER]
        industry = [i for i in all_items if i.source_type == SourceType.RSS_ARTICLE
                     and i.metadata.get("category") in ("industry", "news")]
        social = [i for i in all_items if i.source_type in (SourceType.REDDIT_POST, SourceType.HACKER_NEWS)]
        # Academic RSS goes with papers
        academic_rss = [i for i in all_items if i.source_type == SourceType.RSS_ARTICLE
                        and i.metadata.get("category") == "academic"]

        logger.info(
            "Classification: papers=%d, industry=%d, social=%d, academic_rss=%d",
            len(papers), len(industry), len(social), len(academic_rss),
        )

        # Analyze each category with sequential indexing
        all_analyzed: list[AnalyzedItem] = []
        current_index = 1

        if papers or academic_rss:
            paper_items = papers + academic_rss
            analyzed = await self.paper_analyzer.analyze(paper_items, start_index=current_index)
            all_analyzed.extend(analyzed)
            current_index += len(analyzed)

        if industry:
            analyzed = await self.industry_analyzer.analyze(industry, start_index=current_index)
            all_analyzed.extend(analyzed)
            current_index += len(analyzed)

        if social:
            analyzed = await self.social_analyzer.analyze(social, start_index=current_index)
            all_analyzed.extend(analyzed)
            current_index += len(analyzed)

        # Save analyzed items
        self.store.save_analyzed_items(target_date, all_analyzed)
        logger.info("Analysis complete: %d items analyzed", len(all_analyzed))
        return all_analyzed

    # --- Phase 3: Overview Report ---

    async def generate_overview(self, target_date: date) -> tuple[DailyOverview, str]:
        """Generate Stage 1 overview report."""
        logger.info("=== Phase 3: Generating overview report for %s ===", target_date)

        # Load analyzed items
        items = self._load_analyzed(target_date)
        if not items:
            logger.warning("No analyzed data for %s. Run 'analyze' first.", target_date)
            return DailyOverview(date=target_date, summary="No data.", total_items=0), ""

        return await self.overview_reporter.generate(target_date, items)

    # --- Phase 4: Deep Dive ---

    async def generate_deep_dive(
        self, target_date: date, item_indices: list[int]
    ) -> tuple[DeepDiveReport, str]:
        """Generate Stage 2 deep dive report for selected items."""
        logger.info("=== Phase 4: Generating deep dive for %s, items=%s ===", target_date, item_indices)

        items = self._load_analyzed(target_date)
        if not items:
            logger.warning("No analyzed data for %s", target_date)
            return DeepDiveReport(date=target_date, selected_items=item_indices), ""

        return await self.deep_dive_reporter.generate(target_date, item_indices, items)

    # --- Full Pipeline ---

    async def run(self, target_date: date) -> Path:
        """Execute full pipeline: collect → analyze → overview report."""
        await self.collect(target_date)
        await self.analyze(target_date)
        overview, markdown = await self.generate_overview(target_date)
        output_path = Path("output") / target_date.isoformat() / "daily_report.md"
        logger.info("=== Pipeline complete. Report at %s ===", output_path)
        return output_path

    # --- Helpers ---

    def _load_analyzed(self, target_date: date) -> list[AnalyzedItem]:
        """Load analyzed items from storage."""
        raw_data = self.store.load_analyzed_items(target_date)
        if not raw_data:
            return []

        items = []
        for item_data in raw_data:
            try:
                items.append(AnalyzedItem.model_validate(item_data))
            except Exception as e:
                logger.debug("Skipping invalid analyzed item: %s", e)
        return items

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
                "rss_feeds": len(self.config.rss.feeds),
                "reddit_subreddits": self.config.reddit.subreddits,
                "hn_min_score": self.config.hackernews.min_score,
            },
            "data": {
                "raw_dates": [d.isoformat() for d in raw_dates],
                "analyzed_dates": [d.isoformat() for d in analyzed_dates],
                "report_dates": [d.isoformat() for d in report_dates],
            },
        }
