"""Tests for DeepDiveRegistryManager."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from src.models.registry import RegistryAttribute, RegistryEntry
from src.models.report import DeepAnalysis, DeepDiveReport, DeepSection
from src.registry.manager import DeepDiveRegistryManager
from src.storage.local_store import LocalStore
from src.storage.registry_store import RegistryStore


def _make_manager(mock_llm: MagicMock, tmp_path: Path) -> DeepDiveRegistryManager:
    local_store = LocalStore(tmp_path / "data")
    registry_store = RegistryStore(tmp_path / "records")
    return DeepDiveRegistryManager(mock_llm, store=registry_store, local_store=local_store)


class TestDeepDiveRegistryManager:
    def test_register_from_deep_dive_uses_overview_snippet(
        self, mock_llm: MagicMock, tmp_path: Path, sample_analyzed_paper
    ) -> None:
        manager = _make_manager(mock_llm, tmp_path)
        manager.local_store.save_json(
            "reports/2026-03-25/overview_snippets.json",
            [
                {
                    "index": 1,
                    "title": sample_analyzed_paper.source_item.title,
                    "summary_markdown": "**链接：** https://arxiv.org/abs/2603.12345\n\nA useful summary",
                }
            ],
        )
        mock_llm.generate_json_with_template.return_value = {
            "keywords": ["多智能体", "Agent", "自动化"],
            "attribute": "论文",
        }
        report = DeepDiveReport(
            date=date(2026, 3, 25),
            selected_items=[1],
            analyses=[
                DeepAnalysis(
                    index=1,
                    title=sample_analyzed_paper.source_item.title,
                    source_type="arxiv_paper",
                    sections=[DeepSection(heading="研究背景与动机", content="A useful summary")],
                    references=["https://arxiv.org/abs/2603.12345"],
                )
            ],
        )
        items_index = [
            {"index": 1, "source_item": sample_analyzed_paper.source_item.model_dump(mode="json")},
        ]

        count = manager.register_from_deep_dive(date(2026, 3, 25), report, items_index)
        entries = manager.store.load_month_entries("2026-03")

        assert count == 1
        assert len(entries) == 1
        assert entries[0].record_id == "20260325-001"
        assert entries[0].keywords == ["多智能体", "Agent", "自动化"]
        assert entries[0].attribute == RegistryAttribute.PAPER
        assert entries[0].summary_ref == "SUM-20260325-001"
        assert "A useful summary" in entries[0].summary_markdown

    def test_register_uses_fallback_when_llm_fails(
        self, mock_llm: MagicMock, tmp_path: Path, sample_analyzed_social
    ) -> None:
        manager = _make_manager(mock_llm, tmp_path)
        mock_llm.generate_json_with_template.side_effect = RuntimeError("LLM failed")
        report = DeepDiveReport(
            date=date(2026, 3, 25),
            selected_items=[3],
            analyses=[
                DeepAnalysis(
                    index=3,
                    title=sample_analyzed_social.source_item.title,
                    source_type="hacker_news",
                    sections=[DeepSection(heading="事件/项目概述", content="Summary")],
                    references=[],
                )
            ],
        )
        items_index = [
            {"index": 3, "source_item": sample_analyzed_social.source_item.model_dump(mode="json")},
        ]

        manager.register_from_deep_dive(date(2026, 3, 25), report, items_index)
        entries = manager.store.load_month_entries("2026-03")

        assert len(entries) == 1
        assert entries[0].keywords == []
        assert entries[0].attribute == RegistryAttribute.PROJECT
        assert entries[0].summary_markdown.startswith("**链接：**")

    def test_find_entries_prefers_keyword_matches(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        manager = _make_manager(mock_llm, tmp_path)
        manager.store.upsert_entries([
            RegistryEntry(
                date=date(2026, 3, 25),
                record_id="20260325-001",
                title="Agent safety framework",
                keywords=["agent safety", "multi-agent"],
                attribute=RegistryAttribute.PAPER,
                summary_ref="SUM-20260325-001",
                summary_markdown="summary one",
            ),
            RegistryEntry(
                date=date(2026, 3, 20),
                record_id="20260320-002",
                title="Other item",
                keywords=["tooling"],
                attribute=RegistryAttribute.PROJECT,
                summary_ref="SUM-20260320-002",
                summary_markdown="summary two",
            ),
        ])

        method, matches = manager.find_entries("agent safety", limit=5)

        assert method == "keywords"
        assert [entry.record_id for entry in matches] == ["20260325-001"]
        mock_llm.generate_json_with_template.assert_not_called()

    def test_find_entries_uses_summary_fallback(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        manager = _make_manager(mock_llm, tmp_path)
        manager.store.upsert_entries([
            RegistryEntry(
                date=date(2026, 3, 25),
                record_id="20260325-001",
                title="Agent safety framework",
                keywords=["framework"],
                attribute=RegistryAttribute.PAPER,
                summary_ref="SUM-20260325-001",
                summary_markdown="This summary discusses compiler ergonomics in detail.",
            )
        ])

        method, matches = manager.find_entries("compiler ergonomics", limit=5)

        assert method == "summary"
        assert [entry.record_id for entry in matches] == ["20260325-001"]
        mock_llm.generate_json_with_template.assert_not_called()

    def test_find_entries_uses_llm_fallback(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        manager = _make_manager(mock_llm, tmp_path)
        manager.store.upsert_entries([
            RegistryEntry(
                date=date(2026, 3, 25),
                record_id="20260325-001",
                title="Agent safety framework",
                keywords=["framework"],
                attribute=RegistryAttribute.PAPER,
                summary_ref="SUM-20260325-001",
                summary_markdown="summary one",
            )
        ])
        mock_llm.generate_json_with_template.return_value = {
            "record_ids": ["20260325-001"],
        }

        method, matches = manager.find_entries("a completely different topic", limit=5)

        assert method == "llm"
        assert [entry.record_id for entry in matches] == ["20260325-001"]
        mock_llm.generate_json_with_template.assert_called_once()
