"""Tests for CLI commands."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.cli import app
from src.models.registry import InterestStatus, RegistryAttribute, RegistryEntry

runner = CliRunner()


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.store = MagicMock()
    orch.store.has_raw_data.return_value = False
    orch.store.has_analyzed_data.return_value = False
    orch.store.layer_relative_path.side_effect = lambda layer, d, filename: f"{layer}/{d.strftime('%Y-%m')}/{d.isoformat()}/{filename}"
    orch.store.output_path.side_effect = lambda d, filename: Path("output") / d.strftime("%Y-%m") / d.isoformat() / filename
    orch.collect = AsyncMock(return_value={"arxiv": [], "hackernews": []})
    orch.generate_overview = AsyncMock(return_value=(MagicMock(total_items=0), ""))
    orch.generate_deep_dive = AsyncMock(return_value=(MagicMock(analyses=[]), ""))
    orch.run = AsyncMock(return_value=Path("output/2026-03/2026-03-10/daily_report.md"))
    orch.get_status.return_value = {
        "llm_provider": "anthropic",
        "llm_model": "test-model",
        "collectors": [
            "arxiv",
            "hackernews",
            "youtube",
            "bilibili",
            "semantic_scholar",
            "github_trending",
            "product_hunt",
            "tavily",
        ],
        "config": {
            "arxiv_categories": ["cs.AI"],
            "hn_min_score": 50,
            "youtube_channels": 3,
            "bilibili_users": 0,
            "semantic_scholar_topics": ["large language models"],
            "github_trending_languages": ["python"],
            "product_hunt_topics": ["artificial-intelligence"],
            "tavily_searches": 5,
        },
        "data": {
            "raw_dates": ["2026-03-10"],
            "analyzed_dates": [],
            "report_dates": [],
        },
    }
    orch.registry_manager = MagicMock()
    return orch


class TestCLI:
    def test_get_orchestrator_uses_openai_key(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-should-not-be-used")

        with patch("src.orchestrator.DailyReportOrchestrator") as mock_orch_cls:
            mock_orch_cls.return_value = MagicMock()
            from src.cli import _get_orchestrator
            _ = _get_orchestrator()

            kwargs = mock_orch_cls.call_args.kwargs
            assert kwargs["llm_provider"] == "openai"
            assert kwargs["api_key"] == "openai-test-key"

    def test_get_orchestrator_defaults_to_anthropic(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-key")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-should-not-be-used")

        with patch("src.orchestrator.DailyReportOrchestrator") as mock_orch_cls:
            mock_orch_cls.return_value = MagicMock()
            from src.cli import _get_orchestrator
            _ = _get_orchestrator()

            kwargs = mock_orch_cls.call_args.kwargs
            assert kwargs["llm_provider"] == "anthropic"
            assert kwargs["api_key"] == "anthropic-test-key"

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "dailyreport" in result.output.lower() or "daily" in result.output.lower()

    def test_collect_command(self, mock_orchestrator):
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["collect"])

        assert result.exit_code == 0
        assert "Collecting" in result.output

    def test_collect_with_date(self, mock_orchestrator):
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["collect", "--date", "2026-03-10"])

        assert result.exit_code == 0
        mock_orchestrator.collect.assert_called_once()

    def test_collect_with_sources(self, mock_orchestrator):
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["collect", "--sources", "arxiv,hackernews"])

        assert result.exit_code == 0

    def test_report_command(self, mock_orchestrator):
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["report"])

        assert result.exit_code == 0

    def test_deep_dive_command(self, mock_orchestrator):
        mock_orchestrator.store.has_analyzed_data.return_value = True
        mock_orchestrator.store.load_json.return_value = [{"index": 1, "source_item": {}}]
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["deep-dive", "--items", "1,2,3"])

        assert result.exit_code == 0

    def test_deep_dive_no_data(self, mock_orchestrator):
        mock_orchestrator.store.load_json.return_value = None
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["deep-dive", "--items", "1"])

        assert result.exit_code == 1

    def test_deep_dive_invalid_index(self, mock_orchestrator):
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["deep-dive", "--items", "abc"])

        assert result.exit_code == 1

    def test_run_command(self, mock_orchestrator):
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["run"])

        assert result.exit_code == 0
        assert "Pipeline complete" in result.output

    def test_status_command(self, mock_orchestrator):
        with patch("src.cli._get_orchestrator", return_value=mock_orchestrator):
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "test-model" in result.output

    def test_registry_show_command(self):
        mock_store = MagicMock()
        mock_store.load_all_entries.return_value = [
            RegistryEntry(
                date=date(2026, 3, 25),
                record_id="20260325-001",
                title="Test registry item",
                keywords=["Agent", "Automation"],
                attribute=RegistryAttribute.PROJECT,
                summary_ref="SUM-20260325-001",
                summary_markdown="Summary",
                interest_statuses=[InterestStatus.STAR, InterestStatus.QUESTION],
            )
        ]

        with patch("src.cli._get_registry_store", return_value=mock_store):
            result = runner.invoke(app, ["registry", "show"])

        assert result.exit_code == 0
        mock_store.load_all_entries.assert_called_once()

    def test_registry_show_with_month(self):
        mock_store = MagicMock()
        mock_store.load_month_entries.return_value = []

        with patch("src.cli._get_registry_store", return_value=mock_store):
            result = runner.invoke(app, ["registry", "show", "--month", "2026-03"])

        assert result.exit_code == 0
        mock_store.load_month_entries.assert_called_once_with("2026-03")

    def test_registry_mark_command(self):
        mock_store = MagicMock()
        mock_store.update_interest_statuses.return_value = RegistryEntry(
            date=date(2026, 3, 25),
            record_id="20260325-001",
            title="Test registry item",
            keywords=["Agent"],
            attribute=RegistryAttribute.PROJECT,
            summary_ref="SUM-20260325-001",
            summary_markdown="Summary",
            interest_statuses=[InterestStatus.STAR, InterestStatus.QUESTION],
        )

        with patch("src.cli._get_registry_store", return_value=mock_store):
            result = runner.invoke(app, ["registry", "mark", "--id", "20260325-001", "--status", "star"])

        assert result.exit_code == 0
        assert "20260325-001" in result.output
        mock_store.update_interest_statuses.assert_called_once_with(
            "20260325-001",
            [InterestStatus.STAR],
            mode="add",
        )

    def test_registry_mark_invalid_status(self):
        with patch("src.cli._get_registry_store", return_value=MagicMock()):
            result = runner.invoke(app, ["registry", "mark", "--id", "20260325-001", "--status", "bad"])

        assert result.exit_code == 1

    def test_registry_mark_none_defaults_to_clear(self):
        mock_store = MagicMock()
        mock_store.update_interest_statuses.return_value = RegistryEntry(
            date=date(2026, 3, 25),
            record_id="20260325-001",
            title="Test registry item",
            keywords=["Agent"],
            attribute=RegistryAttribute.PROJECT,
            summary_ref="SUM-20260325-001",
            summary_markdown="Summary",
        )

        with patch("src.cli._get_registry_store", return_value=mock_store):
            result = runner.invoke(app, ["registry", "mark", "--id", "20260325-001", "--status", "none"])

        assert result.exit_code == 0
        mock_store.update_interest_statuses.assert_called_once_with(
            "20260325-001",
            [],
            mode="clear",
        )

    def test_registry_find_command(self):
        mock_manager = MagicMock()
        mock_manager.find_entries.return_value = (
            "keywords",
            [
                RegistryEntry(
                    date=date(2026, 3, 25),
                    record_id="20260325-001",
                    title="Test registry item",
                    keywords=["Agent"],
                    attribute=RegistryAttribute.PROJECT,
                    summary_ref="SUM-20260325-001",
                    summary_markdown="Summary",
                )
            ],
        )
        mock_store = MagicMock()
        mock_store.resolve_month_path.return_value = Path("records/2026-03-record.md")

        with patch("src.cli._get_registry_manager", return_value=mock_manager), patch(
            "src.cli._get_registry_store", return_value=mock_store
        ):
            result = runner.invoke(app, ["registry", "find", "--query", "agent"])

        assert result.exit_code == 0
        assert "2026-03-record.md" in result.output
        mock_manager.find_entries.assert_called_once()
