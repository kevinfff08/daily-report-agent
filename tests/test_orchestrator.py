"""Tests for orchestrator registry integration."""

from __future__ import annotations

import asyncio
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.models.report import DailyOverview, DeepAnalysis, DeepDiveReport, DeepSection
from src.orchestrator import DailyReportOrchestrator


def _workspace_temp_path() -> Path:
    base_dir = Path(".tmp-test-orchestrator")
    base_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = base_dir / f"orchestrator-{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    return temp_dir


"""
def test_generate_deep_dive_registers_entries(sample_arxiv_item) -> None:
    temp_path = _workspace_temp_path()
    registry_manager = MagicMock()
    try:
        orchestrator = DailyReportOrchestrator(
        data_dir=str(temp_path / "data"),
        config_dir=str(temp_path / "config"),
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
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)
"""


def test_generate_deep_dive_registers_entries_local_tmp(sample_arxiv_item) -> None:
    temp_path = _workspace_temp_path()
    registry_manager = MagicMock()
    try:
        orchestrator = DailyReportOrchestrator(
            data_dir=str(temp_path / "data"),
            config_dir=str(temp_path / "config"),
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
                        sections=[DeepSection(heading="summary", content="summary")],
                        references=[],
                    )
                ],
            ),
            "# report",
        ))
        orchestrator.store.save_json(
            orchestrator.store.layer_relative_path("reports", date(2026, 3, 25), "items_index.json"),
            [{"index": 1, "source_item": sample_arxiv_item.model_dump(mode="json")}],
        )

        report, markdown = asyncio.run(orchestrator.generate_deep_dive(date(2026, 3, 25), [1]))

        assert markdown == "# report"
        assert len(report.analyses) == 1
        registry_manager.register_from_deep_dive.assert_called_once()
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


def test_orchestrator_uses_provider_specific_deep_dive_defaults() -> None:
    temp_path = _workspace_temp_path()
    try:
        anthropic_orchestrator = DailyReportOrchestrator(
            data_dir=str(temp_path / "anthropic-data"),
            config_dir=str(temp_path / "config"),
            llm_provider="anthropic",
        )
        openai_orchestrator = DailyReportOrchestrator(
            data_dir=str(temp_path / "openai-data"),
            config_dir=str(temp_path / "config"),
            llm_provider="openai",
        )
        deepseek_orchestrator = DailyReportOrchestrator(
            data_dir=str(temp_path / "deepseek-data"),
            config_dir=str(temp_path / "config"),
            llm_provider="deepseek",
        )

        assert anthropic_orchestrator.paper_max_chars == 40_000
        assert anthropic_orchestrator.deep_dive_max_tokens == 8192
        assert openai_orchestrator.paper_max_chars == 120_000
        assert openai_orchestrator.deep_dive_max_tokens == 12_000
        assert deepseek_orchestrator.paper_max_chars == 120_000
        assert deepseek_orchestrator.deep_dive_max_tokens == 12_000
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


"""
def test_generate_overview_downranks_recent_duplicates_and_saves_debug_json(
    tmp_path: Path,
) -> None:
    orchestrator = DailyReportOrchestrator(
        data_dir=str(tmp_path / "data"),
        config_dir=str(tmp_path / "config"),
    )
    duplicate_item = {
        "id": "github:owner/duplicate-project",
        "source_type": "github_trending",
        "title": "owner/duplicate-project",
        "url": "https://github.com/owner/duplicate-project",
        "authors": ["owner"],
        "published": "2026-03-27T00:00:00+00:00",
        "content_snippet": "Duplicate project still trending strongly.",
        "metadata": {
            "stars_today": 200,
            "stars": 5000,
            "source_name": "GitHub Trending",
        },
    }
    fresh_item = {
        "id": "github:owner/fresh-project",
        "source_type": "github_trending",
        "title": "owner/fresh-project",
        "url": "https://github.com/owner/fresh-project",
        "authors": ["owner"],
        "published": "2026-03-27T00:00:00+00:00",
        "content_snippet": "Fresh project with slightly lower engagement.",
        "metadata": {
            "stars_today": 120,
            "stars": 3000,
            "source_name": "GitHub Trending",
        },
    }
    target_date = date(2026, 3, 27)
    history_date = date(2026, 3, 26)

    orchestrator.store.save_json(
        f"raw/{target_date.isoformat()}/github_trending.json",
        [duplicate_item, fresh_item],
    )
    orchestrator.store.save_json(
        f"reports/{history_date.isoformat()}/items_index.json",
        [{"index": 1, "source_item": duplicate_item}],
    )
    orchestrator.store.save_json(
        f"reports/{history_date.isoformat()}/overview_snippets.json",
        [{"index": 1, "title": duplicate_item["title"], "summary_markdown": "Kept yesterday"}],
    )
    orchestrator.overview_reporter.generate = AsyncMock(
        return_value=(
            DailyOverview(date=target_date, summary="ok", total_items=2),
            "# report",
        )
    )

    overview, markdown = asyncio.run(orchestrator.generate_overview(target_date))

    assert overview.total_items == 2
    assert markdown == "# report"

    call_args = orchestrator.overview_reporter.generate.call_args
    filtered_items = call_args.args[1]
    assert filtered_items[0].id == "github:owner/fresh-project"
    assert filtered_items[1].id == "github:owner/duplicate-project"

    debug_rows = orchestrator.store.load_json(
        f"reports/{target_date.isoformat()}/recent_duplicate_matches.json"
    )
    assert isinstance(debug_rows, list)
    assert debug_rows[0]["item_id"] == "github:owner/duplicate-project"
    assert debug_rows[0]["matches"][0]["match_signal"] == "github_repo"
"""


def test_generate_overview_downranks_recent_duplicates_and_saves_debug_json_local_tmp() -> None:
    temp_path = _workspace_temp_path()
    duplicate_item = {
        "id": "github:owner/duplicate-project",
        "source_type": "github_trending",
        "title": "owner/duplicate-project",
        "url": "https://github.com/owner/duplicate-project",
        "authors": ["owner"],
        "published": "2026-03-27T00:00:00+00:00",
        "content_snippet": "Duplicate project still trending strongly.",
        "metadata": {
            "stars_today": 200,
            "stars": 5000,
            "source_name": "GitHub Trending",
        },
    }
    fresh_item = {
        "id": "github:owner/fresh-project",
        "source_type": "github_trending",
        "title": "owner/fresh-project",
        "url": "https://github.com/owner/fresh-project",
        "authors": ["owner"],
        "published": "2026-03-27T00:00:00+00:00",
        "content_snippet": "Fresh project with slightly lower engagement.",
        "metadata": {
            "stars_today": 120,
            "stars": 3000,
            "source_name": "GitHub Trending",
        },
    }
    target_date = date(2026, 3, 27)
    history_date = date(2026, 3, 26)

    try:
        orchestrator = DailyReportOrchestrator(
            data_dir=str(temp_path / "data"),
            config_dir=str(temp_path / "config"),
        )
        orchestrator.store.save_json(
            orchestrator.store.layer_relative_path("raw", target_date, "github_trending.json"),
            [duplicate_item, fresh_item],
        )
        orchestrator.store.save_json(
            orchestrator.store.layer_relative_path("reports", history_date, "items_index.json"),
            [{"index": 1, "source_item": duplicate_item}],
        )
        orchestrator.store.save_json(
            orchestrator.store.layer_relative_path("reports", history_date, "overview_snippets.json"),
            [{"index": 1, "title": duplicate_item["title"], "summary_markdown": "Kept yesterday"}],
        )
        orchestrator.overview_reporter.generate = AsyncMock(
            return_value=(
                DailyOverview(date=target_date, summary="ok", total_items=2),
                "# report",
            )
        )

        overview, markdown = asyncio.run(orchestrator.generate_overview(target_date))

        assert overview.total_items == 2
        assert markdown == "# report"

        call_args = orchestrator.overview_reporter.generate.call_args
        filtered_items = call_args.args[1]
        assert filtered_items[0].id == "github:owner/fresh-project"
        assert filtered_items[1].id == "github:owner/duplicate-project"

        debug_rows = orchestrator.store.load_json(
            orchestrator.store.layer_relative_path("reports", target_date, "recent_duplicate_matches.json")
        )
        assert isinstance(debug_rows, list)
        assert debug_rows[0]["item_id"] == "github:owner/duplicate-project"
        assert debug_rows[0]["matches"][0]["match_signal"] == "github_repo"
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)
