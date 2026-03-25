"""Tests for RegistryStore."""

from datetime import date
from pathlib import Path

from src.models.registry import InterestStatus, RegistryAttribute, RegistryEntry
from src.storage.registry_store import RegistryStore


def _make_store(tmp_path: Path) -> RegistryStore:
    return RegistryStore(tmp_path / "records")


class TestRegistryStore:
    def test_load_month_entries_creates_monthly_file(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)

        entries = store.load_month_entries("2026-03")

        assert entries == []
        assert (tmp_path / "records" / "2026-03-record.md").exists()

    def test_upsert_month_entries_preserves_interest_status(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        original = RegistryEntry(
            date=date(2026, 3, 25),
            record_id="20260325-001",
            title="Original title",
            keywords=["agent"],
            attribute=RegistryAttribute.PROJECT,
            summary_ref="SUM-20260325-001",
            summary_markdown="Original summary",
            interest_status=InterestStatus.STAR,
        )
        updated = RegistryEntry(
            date=date(2026, 3, 25),
            record_id="20260325-001",
            title="Updated title",
            keywords=["agent", "workflow"],
            attribute=RegistryAttribute.PRODUCT,
            summary_ref="SUM-20260325-001",
            summary_markdown="Updated summary",
        )

        store.upsert_month_entries(date(2026, 3, 25), [original])
        store.upsert_month_entries(date(2026, 3, 25), [updated])
        entries = store.load_month_entries("2026-03")

        assert len(entries) == 1
        assert entries[0].title == "Updated title"
        assert entries[0].record_id == "20260325-001"
        assert entries[0].interest_status == InterestStatus.STAR
        assert entries[0].attribute == RegistryAttribute.PRODUCT
        assert entries[0].summary_markdown == "Updated summary"

    def test_load_all_entries_across_months(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        march_entry = RegistryEntry(
            date=date(2026, 3, 25),
            record_id="20260325-001",
            title="March entry",
            keywords=["agent"],
            attribute=RegistryAttribute.PROJECT,
            summary_ref="SUM-20260325-001",
            summary_markdown="March summary",
        )
        april_entry = RegistryEntry(
            date=date(2026, 4, 1),
            record_id="20260401-001",
            title="April entry",
            keywords=["safety"],
            attribute=RegistryAttribute.PAPER,
            summary_ref="SUM-20260401-001",
            summary_markdown="April summary",
        )

        store.upsert_entries([march_entry, april_entry])
        entries = store.load_all_entries()

        assert [entry.record_id for entry in entries] == ["20260401-001", "20260325-001"]
        assert (tmp_path / "records" / "2026-03-record.md").exists()
        assert (tmp_path / "records" / "2026-04-record.md").exists()

    def test_update_interest_status_across_months(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        entry = RegistryEntry(
            date=date(2026, 4, 1),
            record_id="20260401-001",
            title="Sample title",
            keywords=["multimodal"],
            attribute=RegistryAttribute.PAPER,
            summary_ref="SUM-20260401-001",
            summary_markdown="Sample summary",
        )

        store.upsert_entries([entry])
        updated = store.update_interest_status("20260401-001", InterestStatus.CHECK)

        assert updated.interest_status == InterestStatus.CHECK
        loaded = store.load_month_entries("2026-04")
        assert loaded[0].interest_status == InterestStatus.CHECK

    def test_monthly_file_contains_summary_appendix(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        entry = RegistryEntry(
            date=date(2026, 3, 25),
            record_id="20260325-001",
            title="Sample title",
            keywords=["agent"],
            attribute=RegistryAttribute.PROJECT,
            summary_ref="SUM-20260325-001",
            summary_markdown="**链接：** https://example.com/item\n\n摘要正文",
            source_index=1,
        )

        path = store.upsert_month_entries(date(2026, 3, 25), [entry])
        content = path.read_text(encoding="utf-8")

        assert "## 摘要附录" in content
        assert "### SUM-20260325-001" in content
        assert "<!-- summary-start -->" in content
        assert "摘要正文" in content
