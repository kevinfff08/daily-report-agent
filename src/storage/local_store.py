"""JSON file-based persistence using Pydantic models."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from src.logging_config import get_logger

logger = get_logger("storage")

T = TypeVar("T", bound=BaseModel)


class LocalStore:
    """Manages JSON file storage organized by date."""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create base directory structure."""
        for sub in ["raw", "analyzed", "reports", "cache"]:
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

    def _date_dir(self, layer: str, target_date: date) -> Path:
        """Get date-specific directory for a layer."""
        d = self.data_dir / layer / target_date.isoformat()
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --- Generic methods ---

    def save_model(self, relative_path: str, model: BaseModel) -> Path:
        """Save a Pydantic model as JSON."""
        path = self.data_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("Saved model to %s", path)
        return path

    def load_model(self, relative_path: str, model_class: type[T]) -> T | None:
        """Load a Pydantic model from JSON."""
        path = self.data_dir / relative_path
        if not path.exists():
            logger.debug("File not found: %s", path)
            return None
        try:
            data = path.read_text(encoding="utf-8")
            return model_class.model_validate_json(data)
        except Exception as e:
            logger.error("Failed to load %s: %s", path, e)
            return None

    def save_json(self, relative_path: str, data: dict | list) -> Path:
        """Save raw JSON data."""
        path = self.data_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        logger.debug("Saved JSON to %s", path)
        return path

    def load_json(self, relative_path: str) -> dict | list | None:
        """Load raw JSON data."""
        path = self.data_dir / relative_path
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to load JSON %s: %s", path, e)
            return None

    # --- Convenience methods ---

    def save_raw_items(self, target_date: date, source_name: str, items: list[BaseModel]) -> Path:
        """Save raw collected items for a specific source and date."""
        data = [item.model_dump(mode="json") for item in items]
        return self.save_json(f"raw/{target_date.isoformat()}/{source_name}.json", data)

    def load_raw_items(self, target_date: date, source_name: str) -> list[dict] | None:
        """Load raw collected items for a specific source and date."""
        return self.load_json(f"raw/{target_date.isoformat()}/{source_name}.json")

    def save_analyzed_items(self, target_date: date, items: list[BaseModel]) -> Path:
        """Save analyzed items for a date."""
        data = [item.model_dump(mode="json") for item in items]
        return self.save_json(f"analyzed/{target_date.isoformat()}/analyzed_items.json", data)

    def load_analyzed_items(self, target_date: date) -> list[dict] | None:
        """Load analyzed items for a date."""
        return self.load_json(f"analyzed/{target_date.isoformat()}/analyzed_items.json")

    def save_report(self, target_date: date, filename: str, content: str) -> Path:
        """Save a report markdown file."""
        d = self._date_dir("reports", target_date)
        path = d / filename
        path.write_text(content, encoding="utf-8")
        logger.info("Saved report to %s", path)
        return path

    def save_output(self, target_date: date, filename: str, content: str) -> Path:
        """Save a final output file to output/ directory."""
        output_dir = Path("output") / target_date.isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        logger.info("Saved output to %s", path)
        return path

    def has_raw_data(self, target_date: date) -> bool:
        """Check if raw data exists for a date."""
        raw_dir = self.data_dir / "raw" / target_date.isoformat()
        return raw_dir.exists() and any(raw_dir.iterdir())

    def has_analyzed_data(self, target_date: date) -> bool:
        """Check if analyzed data exists for a date."""
        path = self.data_dir / "analyzed" / target_date.isoformat() / "analyzed_items.json"
        return path.exists()

    def list_dates(self, layer: str = "raw") -> list[date]:
        """List all dates that have data for a given layer."""
        layer_dir = self.data_dir / layer
        if not layer_dir.exists():
            return []
        dates = []
        for d in sorted(layer_dir.iterdir()):
            if d.is_dir():
                try:
                    dates.append(date.fromisoformat(d.name))
                except ValueError:
                    continue
        return dates
