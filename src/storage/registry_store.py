"""Markdown-backed monthly storage for the deep-dive registry."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from src.logging_config import get_logger
from src.models.registry import InterestStatus, RegistryEntry

logger = get_logger("storage.registry")

_SUMMARY_HEADING_RE = re.compile(r"^###\s+(SUM-\d{8}-\d{3})\s*$")
_SUMMARY_LINK_RE = re.compile(r"\[(SUM-\d{8}-\d{3})\]\(#sum-\d{8}-\d{3}\)")
_SUMMARY_START_MARKER = "<!-- summary-start -->"
_SUMMARY_END_MARKER = "<!-- summary-end -->"
_SOURCE_INDEX_RE = re.compile(r"<!-- source_index: (\d+) -->")


class RegistryStore:
    """Persists registry entries in deterministic monthly Markdown files."""

    def __init__(self, base_dir: str | Path = "records"):
        self.base_dir = Path(base_dir)

    def resolve_month_path(self, target_date: date) -> Path:
        """Resolve the monthly registry path for a date."""
        return self.base_dir / f"{target_date.strftime('%Y-%m')}-record.md"

    def load_entries(self) -> list[RegistryEntry]:
        """Backward-compatible alias for loading all entries."""
        return self.load_all_entries()

    def load_month_entries(self, year_month: str) -> list[RegistryEntry]:
        """Load registry entries from a specific monthly file."""
        path = self._ensure_month_file(year_month)
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        table_lines = self._extract_table_lines(lines)
        summary_map, source_index_map = self._parse_summary_appendix(lines)

        entries: list[RegistryEntry] = []
        for line in table_lines[2:]:
            cells = self._split_row(line)
            if len(cells) not in {7, 8}:
                logger.warning("Skipping malformed registry row: %s", line)
                continue

            if len(cells) == 8:
                date_cell, record_id, title, keywords_cell, _links_cell, attribute_cell, summary_cell, status_cell = cells
            else:
                date_cell, record_id, title, keywords_cell, attribute_cell, summary_cell, status_cell = cells

            summary_ref = self._parse_summary_ref(summary_cell)
            try:
                entry = RegistryEntry(
                    date=date.fromisoformat(date_cell),
                    record_id=record_id,
                    title=title,
                    keywords=self._parse_keywords(keywords_cell),
                    attribute=attribute_cell,
                    summary_ref=summary_ref,
                    summary_markdown=summary_map.get(summary_ref, ""),
                    source_index=source_index_map.get(summary_ref),
                    interest_statuses=status_cell,
                )
            except Exception as exc:
                logger.warning("Skipping invalid registry row: %s", exc)
                continue
            entries.append(entry)

        return entries

    def load_all_entries(self) -> list[RegistryEntry]:
        """Load all registry entries across monthly files."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        entries: list[RegistryEntry] = []
        for path in sorted(self.base_dir.glob("*-record.md")):
            if path.name.endswith(".example.md"):
                continue
            year_month = path.name.removesuffix("-record.md")
            entries.extend(self.load_month_entries(year_month))
        return sorted(entries, key=lambda item: (-item.date.toordinal(), item.record_id))

    def save_month_entries(self, target_date: date, entries: list[RegistryEntry]) -> Path:
        """Rewrite a monthly registry file using canonical formatting."""
        year_month = target_date.strftime("%Y-%m")
        path = self._ensure_month_file(year_month)
        sorted_entries = sorted(entries, key=lambda item: (-item.date.toordinal(), item.record_id))

        lines = [self._build_header(year_month).rstrip()]
        for entry in sorted_entries:
            lines.append(self._format_row(entry))

        lines.append("")
        lines.append("## 摘要附录")
        lines.append("")
        for entry in sorted_entries:
            lines.extend(self._format_summary_block(entry))

        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        logger.info("Saved monthly deep-dive registry to %s", path)
        return path

    def upsert_month_entries(self, target_date: date, new_entries: list[RegistryEntry]) -> Path:
        """Insert or update entries for a month while preserving manual interest status."""
        current_entries = self.load_month_entries(target_date.strftime("%Y-%m"))
        by_key = {entry.record_id: entry for entry in current_entries}

        for entry in new_entries:
            key = entry.record_id
            existing = by_key.get(key)
            if existing is not None:
                entry.interest_statuses = list(existing.interest_statuses)
                entry.record_id = existing.record_id
                entry.summary_ref = existing.summary_ref
            by_key[key] = entry

        return self.save_month_entries(target_date, list(by_key.values()))

    def upsert_entries(self, new_entries: list[RegistryEntry]) -> list[Path]:
        """Backward-compatible upsert grouped by month."""
        groups: dict[str, list[RegistryEntry]] = defaultdict(list)
        for entry in new_entries:
            groups[entry.month_key].append(entry)

        saved_paths: list[Path] = []
        for month_key, month_entries in groups.items():
            target_date = date.fromisoformat(f"{month_key}-01")
            saved_paths.append(self.upsert_month_entries(target_date, month_entries))
        return saved_paths

    def update_interest_status(self, record_id: str, status: InterestStatus) -> RegistryEntry:
        """Backward-compatible alias for appending a single status."""
        return self.update_interest_statuses(record_id, [status], mode="add")

    def update_interest_statuses(
        self,
        record_id: str,
        statuses: list[InterestStatus],
        mode: str = "add",
    ) -> RegistryEntry:
        """Update the interest statuses for a single record across months."""
        for path in sorted(self.base_dir.glob("*-record.md")):
            if path.name.endswith(".example.md"):
                continue
            year_month = path.name.removesuffix("-record.md")
            entries = self.load_month_entries(year_month)
            for entry in entries:
                if entry.record_id == record_id:
                    entry.interest_statuses = self._merge_interest_statuses(
                        entry.interest_statuses,
                        statuses,
                        mode,
                    )
                    self.save_month_entries(entry.date, entries)
                    return entry

        raise KeyError(f"Registry entry not found: {record_id}")

    def _ensure_month_file(self, year_month: str) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / f"{year_month}-record.md"
        if not path.exists():
            path.write_text(self._build_header(year_month), encoding="utf-8")
        return path

    @staticmethod
    def _build_header(year_month: str) -> str:
        return (
            f"# Deep Dive 长期关注台账（{year_month}）\n\n"
            "> 自动登记每次 `deep-dive` 生成的条目。\n"
            "> 可直接手动编辑“我的关注状态”列，或使用 CLI 命令维护。\n"
            "> 状态说明：`*` = 非常关注，`?` = 需要进一步学习，`✓` = 可能有用；可同时保留多个状态。\n\n"
            "| 日期 | 记录ID | 标题 | 关键词 | 属性 | 摘要 | 我的关注状态 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |"
        )

    @staticmethod
    def _extract_table_lines(lines: list[str]) -> list[str]:
        table_lines: list[str] = []
        for line in lines:
            if line.strip() == "## 摘要附录":
                break
            if line.strip().startswith("|"):
                table_lines.append(line)
        return table_lines

    @staticmethod
    def _split_row(line: str) -> list[str]:
        stripped = line.strip().strip("|")
        return [cell.strip() for cell in stripped.split("|")]

    @staticmethod
    def _parse_keywords(value: str) -> list[str]:
        if not value:
            return []
        return [part.strip() for part in value.split(" / ") if part.strip()]

    @staticmethod
    def _parse_summary_ref(value: str) -> str:
        if not value:
            return ""
        match = _SUMMARY_LINK_RE.search(value)
        if match:
            return match.group(1)
        return value.strip()

    @staticmethod
    def _sanitize_cell(text: str) -> str:
        return " ".join(text.replace("|", " / ").replace("\n", " ").split()).strip()

    @staticmethod
    def _merge_interest_statuses(
        existing: list[InterestStatus],
        updates: list[InterestStatus],
        mode: str,
    ) -> list[InterestStatus]:
        normalized_existing = [status for status in InterestStatus.ordered() if status in existing]
        normalized_updates = [status for status in InterestStatus.ordered() if status in updates]

        if mode == "clear":
            return []
        if mode == "set":
            return normalized_updates
        if mode == "remove":
            return [status for status in normalized_existing if status not in normalized_updates]

        merged = list(normalized_existing)
        for status in normalized_updates:
            if status not in merged:
                merged.append(status)
        return [status for status in InterestStatus.ordered() if status in merged]

    def _format_row(self, entry: RegistryEntry) -> str:
        keywords = " / ".join(self._sanitize_cell(keyword) for keyword in entry.keywords)
        summary_link = f"[{entry.summary_ref}](#{entry.summary_ref.lower()})"
        return (
            f"| {entry.date.isoformat()} | {entry.record_id} | "
            f"{self._sanitize_cell(entry.title)} | {keywords} | "
            f"{entry.attribute.value} | {summary_link} | {entry.interest_status_display} |"
        )

    def _format_summary_block(self, entry: RegistryEntry) -> list[str]:
        summary_body = entry.summary_markdown.strip() or "（无摘要）"
        block = [
            f"### {entry.summary_ref}",
            f"<!-- record_id: {entry.record_id} -->",
        ]
        if entry.source_index is not None:
            block.append(f"<!-- source_index: {entry.source_index} -->")
        block.extend([
            _SUMMARY_START_MARKER,
            summary_body,
            _SUMMARY_END_MARKER,
            "",
        ])
        return block

    @staticmethod
    def _parse_summary_appendix(lines: list[str]) -> tuple[dict[str, str], dict[str, int]]:
        summary_map: dict[str, str] = {}
        source_index_map: dict[str, int] = {}
        current_ref: str | None = None
        collecting = False
        current_lines: list[str] = []

        def flush_current() -> None:
            nonlocal current_ref, current_lines
            if current_ref is None:
                return
            summary_map[current_ref] = "\n".join(current_lines).strip()
            current_ref = None
            current_lines = []

        for line in lines:
            heading_match = _SUMMARY_HEADING_RE.match(line.strip())
            if heading_match:
                flush_current()
                current_ref = heading_match.group(1)
                collecting = False
                continue

            if current_ref is None:
                continue

            source_index_match = _SOURCE_INDEX_RE.match(line.strip())
            if source_index_match:
                source_index_map[current_ref] = int(source_index_match.group(1))
                continue

            if line.strip() == _SUMMARY_START_MARKER:
                collecting = True
                current_lines = []
                continue

            if line.strip() == _SUMMARY_END_MARKER:
                collecting = False
                continue

            if collecting:
                current_lines.append(line)

        flush_current()
        return summary_map, source_index_map
