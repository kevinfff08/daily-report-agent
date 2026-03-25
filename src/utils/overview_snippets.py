"""Utilities for extracting structured overview snippets from daily_report markdown."""

from __future__ import annotations

import re

from src.models.report import OverviewSnippet

_ITEM_HEADING_RE = re.compile(r"^###\s+(?:⭐\s+)?\[(\d+)\]\s+(.+?)\s*$")
_INDEX_SECTION_MARKERS = {"## 候选条目索引", "## 索引表"}


def extract_overview_snippets(markdown: str) -> list[OverviewSnippet]:
    """Parse daily overview markdown into per-item summary blocks."""
    snippets: list[OverviewSnippet] = []
    current_index: int | None = None
    current_title = ""
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_index, current_title, current_lines
        if current_index is None:
            return

        body_lines = list(current_lines)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        while body_lines and body_lines[-1].strip() == "---":
            body_lines.pop()
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)

        snippets.append(
            OverviewSnippet(
                index=current_index,
                title=current_title,
                summary_markdown="\n".join(body_lines).strip(),
            )
        )
        current_index = None
        current_title = ""
        current_lines = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line in _INDEX_SECTION_MARKERS:
            flush_current()
            break

        match = _ITEM_HEADING_RE.match(line)
        if match:
            flush_current()
            current_index = int(match.group(1))
            current_title = match.group(2).strip()
            continue

        if current_index is not None:
            current_lines.append(raw_line)

    flush_current()
    return snippets
