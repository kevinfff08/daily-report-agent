"""Tests for CLI commands."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.store = MagicMock()
    orch.store.has_raw_data.return_value = False
    orch.store.has_analyzed_data.return_value = False
    orch.collect = AsyncMock(return_value={"arxiv": [], "hackernews": []})
    orch.analyze = AsyncMock(return_value=[])
    orch.generate_overview = AsyncMock(return_value=(
        MagicMock(total_items=0), ""
    ))
    orch.generate_deep_dive = AsyncMock(return_value=(
        MagicMock(analyses=[]), ""
    ))
    orch.run = AsyncMock(return_value=Path("output/2026-03-10/daily_report.md"))
    orch.get_status.return_value = {
        "llm_provider": "anthropic",
        "llm_model": "test-model",
        "collectors": ["arxiv", "hackernews", "youtube", "bilibili",
                        "semantic_scholar", "github_trending", "product_hunt", "tavily"],
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
