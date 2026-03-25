"""Tests for orchestrator registry integration."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.models.report import DeepAnalysis, DeepDiveReport, DeepSection
from src.orchestrator import DailyReportOrchestrator


def test_generate_deep_dive_registers_entries(tmp_path: Path, sample_arxiv_item) -> None:
    registry_manager = MagicMock()
    orchestrator = DailyReportOrchestrator(
        data_dir=str(tmp_path / "data"),
        config_dir=str(tmp_path / "config"),
        registry_manager=registry_manager,
    )
    orchestrator.deep_dive_reporter.generate = AsyncMock(return_value=(
        DeepDiveReport(
            date=date(2026, 3, 25),
            selected_items=[1],
            analyses=[
                DeepAnalysis(
                    index=1,
                    title=sample_arxiv_item.title,
                    source_type="arxiv_paper",
                    sections=[DeepSection(heading="研究背景与动机", content="summary")],
                    references=[],
                )
            ],
        ),
        "# report",
    ))
    orchestrator.store.save_json(
        "reports/2026-03-25/items_index.json",
        [{"index": 1, "source_item": sample_arxiv_item.model_dump(mode="json")}],
    )

    report, markdown = asyncio.run(orchestrator.generate_deep_dive(date(2026, 3, 25), [1]))

    assert markdown == "# report"
    assert len(report.analyses) == 1
    registry_manager.register_from_deep_dive.assert_called_once()
