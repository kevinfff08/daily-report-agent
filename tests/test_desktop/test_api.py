from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.desktop.api import DailyReportDesktopAPI
from src.models.registry import InterestStatus, RegistryAttribute, RegistryEntry
from src.storage.local_store import LocalStore
from src.storage.registry_store import RegistryStore


def _wait_for_job(api: DailyReportDesktopAPI, job_id: str) -> dict:
    for _ in range(50):
        result = api.get_job(job_id)
        assert result["ok"] is True
        job = result["job"]
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for desktop job")


def test_start_task_rejects_unknown_action(tmp_path: Path) -> None:
    api = DailyReportDesktopAPI(default_date="2026-03-10", project_root=tmp_path)

    result = api.start_task("shell", {})

    assert result["ok"] is False
    assert "Unsupported" in result["error"]


def test_list_items_reads_items_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_arxiv_item,
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    store = LocalStore(data_dir)
    target_date = date(2026, 3, 10)
    store.save_json(
        store.layer_relative_path("reports", target_date, "items_index.json"),
        [{"index": 1, "source_item": sample_arxiv_item.model_dump(mode="json")}],
    )
    api = DailyReportDesktopAPI(default_date=target_date, project_root=tmp_path)

    result = api.list_items("2026-03-10")

    assert result["ok"] is True
    assert result["items"][0]["indexLabel"] == "001"
    assert result["items"][0]["category"] == "\u8bba\u6587"
    assert result["items"][0]["source"] == "arXiv cs.AI"


def test_load_report_only_reads_allowed_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    target_dir = tmp_path / "output" / "2026-03" / "2026-03-10"
    target_dir.mkdir(parents=True)
    report_path = target_dir / "daily_report.html"
    report_path.write_text("<!doctype html><title>Report</title>", encoding="utf-8")
    outside_path = tmp_path / "outside.html"
    outside_path.write_text("<html></html>", encoding="utf-8")
    api = DailyReportDesktopAPI(default_date="2026-03-10", project_root=tmp_path)

    result = api.load_report("overview", "2026-03-10")

    assert result["ok"] is True
    assert "Report" in result["html"]
    with pytest.raises(PermissionError):
        api._read_allowed_html(outside_path)


def test_html_job_renders_existing_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    report_dir = tmp_path / "output" / "2026-03" / "2026-03-10"
    report_dir.mkdir(parents=True)
    (report_dir / "daily_report.md").write_text("# Daily\n\n## Section", encoding="utf-8")
    api = DailyReportDesktopAPI(default_date="2026-03-10", project_root=tmp_path)

    started = api.start_task("html", {"date": "2026-03-10"})
    job = _wait_for_job(api, started["job_id"])

    assert job["status"] == "succeeded"
    assert (report_dir / "daily_report.html").exists()


def test_deep_dive_job_merges_checked_and_extra_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_arxiv_item,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    store = LocalStore(tmp_path / "data")
    target_date = date(2026, 3, 10)
    store.save_json(
        store.layer_relative_path("reports", target_date, "items_index.json"),
        [{"index": 1, "source_item": sample_arxiv_item.model_dump(mode="json")}],
    )

    class FakeOrchestrator:
        def __init__(self) -> None:
            self.store = store
            self.received_indices: list[int] = []

        async def generate_deep_dive(self, _target_date: date, indices: list[int]):
            self.received_indices = indices
            return MagicMock(analyses=[object()]), "# deep"

    fake = FakeOrchestrator()
    api = DailyReportDesktopAPI(
        default_date=target_date,
        orchestrator_factory=lambda: fake,
        project_root=tmp_path,
    )

    started = api.start_task("deep_dive", {
        "date": "2026-03-10",
        "items": [2],
        "extraItems": "1,2,3",
    })
    job = _wait_for_job(api, started["job_id"])

    assert job["status"] == "succeeded"
    assert fake.received_indices == [1, 2, 3]


def test_update_registry_status_writes_markdown_and_refreshes_html(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path / "records")
    entry = RegistryEntry(
        date=date(2026, 3, 25),
        record_id="20260325-001",
        title="Sample",
        keywords=["agent"],
        attribute=RegistryAttribute.PROJECT,
        summary_ref="SUM-20260325-001",
        summary_markdown="Summary",
    )
    store.upsert_entries([entry])
    api = DailyReportDesktopAPI(
        default_date="2026-03-25",
        registry_store_factory=lambda: store,
        project_root=tmp_path,
    )

    result = api.update_registry_status("20260325-001", ["star", "check"], mode="set")

    assert result["ok"] is True
    entries = store.load_month_entries("2026-03")
    assert entries[0].interest_statuses == [InterestStatus.STAR, InterestStatus.CHECK]
    assert (tmp_path / "records" / "2026-03-record.html").exists()
