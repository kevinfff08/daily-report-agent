"""Tests for LocalStore."""

from datetime import date
from pathlib import Path

import pytest

from src.models.report import DailyOverview
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore


class TestLocalStore:
    def test_init_creates_dirs(self, store, tmp_data_dir):
        assert (tmp_data_dir / "raw").exists()
        assert (tmp_data_dir / "analyzed").exists()
        assert (tmp_data_dir / "reports").exists()
        assert (tmp_data_dir / "cache").exists()

    def test_save_and_load_json(self, store):
        data = {"key": "value", "count": 42}
        store.save_json("test/data.json", data)

        loaded = store.load_json("test/data.json")
        assert loaded == data

    def test_load_json_not_found(self, store):
        assert store.load_json("nonexistent.json") is None

    def test_save_and_load_model(self, store):
        overview = DailyOverview(
            date=date(2026, 3, 10),
            summary="Test summary",
            total_items=5,
        )
        store.save_model("test/model.json", overview)

        loaded = store.load_model("test/model.json", DailyOverview)
        assert loaded is not None
        assert loaded.date == date(2026, 3, 10)
        assert loaded.summary == "Test summary"
        assert loaded.total_items == 5

    def test_load_model_not_found(self, store):
        assert store.load_model("nonexistent.json", DailyOverview) is None

    def test_save_and_load_raw_items(self, store, sample_arxiv_item):
        target_date = date(2026, 3, 10)
        store.save_raw_items(target_date, "arxiv", [sample_arxiv_item])

        loaded = store.load_raw_items(target_date, "arxiv")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["id"] == "arxiv:2603.12345"
        assert loaded[0]["title"] == "Attention Is All You Need (Again)"

    def test_load_raw_items_not_found(self, store):
        assert store.load_raw_items(date(2026, 1, 1), "arxiv") is None

    def test_save_and_load_analyzed_items(self, store, sample_analyzed_paper):
        target_date = date(2026, 3, 10)
        store.save_analyzed_items(target_date, [sample_analyzed_paper])

        loaded = store.load_analyzed_items(target_date)
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["index"] == 1
        assert loaded[0]["category"] == "论文"

    def test_save_report(self, store):
        target_date = date(2026, 3, 10)
        path = store.save_report(target_date, "test.md", "# Test Report")

        assert path.exists()
        assert path.read_text(encoding="utf-8") == "# Test Report"
        assert "2026-03" in str(path)
        assert "2026-03-10" in str(path)
        assert "reports" in str(path)

    def test_save_output(self, store, tmp_path, monkeypatch):
        target_date = date(2026, 3, 10)
        # Change working directory for output path
        monkeypatch.chdir(tmp_path)
        path = store.save_output(target_date, "report.md", "# Output")

        assert path.exists()
        assert path.read_text(encoding="utf-8") == "# Output"
        assert "2026-03" in str(path)

    def test_has_raw_data(self, store, sample_arxiv_item):
        target_date = date(2026, 3, 10)
        assert store.has_raw_data(target_date) is False

        store.save_raw_items(target_date, "arxiv", [sample_arxiv_item])
        assert store.has_raw_data(target_date) is True

    def test_has_analyzed_data(self, store, sample_analyzed_paper):
        target_date = date(2026, 3, 10)
        assert store.has_analyzed_data(target_date) is False

        store.save_analyzed_items(target_date, [sample_analyzed_paper])
        assert store.has_analyzed_data(target_date) is True

    def test_list_dates(self, store, sample_arxiv_item):
        assert store.list_dates("raw") == []

        store.save_raw_items(date(2026, 3, 10), "arxiv", [sample_arxiv_item])
        store.save_raw_items(date(2026, 3, 9), "arxiv", [sample_arxiv_item])

        dates = store.list_dates("raw")
        assert len(dates) == 2
        assert date(2026, 3, 9) in dates
        assert date(2026, 3, 10) in dates

    def test_list_dates_sorted(self, store, sample_arxiv_item):
        for d in [date(2026, 3, 10), date(2026, 3, 8), date(2026, 3, 9)]:
            store.save_raw_items(d, "arxiv", [sample_arxiv_item])

        dates = store.list_dates("raw")
        assert dates == sorted(dates)

    def test_list_dates_invalid_dir_names_ignored(self, store, tmp_data_dir):
        (tmp_data_dir / "raw" / "not-a-date").mkdir(parents=True)
        (tmp_data_dir / "raw" / "2026-03" / "2026-03-10").mkdir(parents=True)

        dates = store.list_dates("raw")
        assert len(dates) == 1
        assert dates[0] == date(2026, 3, 10)
