"""Base class for all data collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.logging_config import get_logger
from src.models.source import SourceItem
from src.storage.local_store import LocalStore


class BaseCollector(ABC):
    """Abstract base class for data collectors."""

    source_name: str = "unknown"

    def __init__(self, store: LocalStore, config: dict | None = None):
        self.store = store
        self.config = config or {}
        self.logger = get_logger(f"collectors.{self.__class__.__name__}")

    @abstractmethod
    async def collect(self, target_date: date) -> list[SourceItem]:
        """Collect items for the given date. Subclasses must implement."""
        ...

    async def collect_and_save(self, target_date: date) -> list[SourceItem]:
        """Collect items and persist them."""
        self.logger.info("Collecting from %s for %s...", self.source_name, target_date)
        try:
            items = await self.collect(target_date)
            if items:
                self.store.save_raw_items(target_date, self.source_name, items)
                self.logger.info("Collected %d items from %s", len(items), self.source_name)
            else:
                self.logger.info("No items collected from %s", self.source_name)
            return items
        except Exception as e:
            self.logger.error("Failed to collect from %s: %s", self.source_name, e)
            return []
