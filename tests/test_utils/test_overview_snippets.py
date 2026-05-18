"""Tests for overview snippet extraction."""

from src.utils.overview_snippets import extract_overview_snippets


def test_extract_overview_snippets_parses_selected_items() -> None:
    markdown = """# 每日情报概览 — 2026-03-25

## 论文

### ⭐ [001] Example Paper
**链接：** https://example.com/paper

First summary paragraph.

---

### [014] Example Two
**链接：** https://example.com/two

Second summary paragraph.

## 候选条目索引
"""

    snippets = extract_overview_snippets(markdown)

    assert [snippet.index for snippet in snippets] == [1, 14]
    assert snippets[0].title == "Example Paper"
    assert "First summary paragraph." in snippets[0].summary_markdown
    assert "Second summary paragraph." in snippets[1].summary_markdown


def test_extract_overview_snippets_stops_item_at_next_major_section() -> None:
    markdown = """# 每日情报概览 — 2026-05-15

## 业界动态

### [049] Raindrop Workshop
链接：https://example.com/raindrop

Item summary.

## 社区热点

## 今日要点

This section should not enter item 49.

### [061] Another Item
Another summary.

## 候选条目索引
"""

    snippets = extract_overview_snippets(markdown)

    assert [snippet.index for snippet in snippets] == [49, 61]
    assert "Item summary." in snippets[0].summary_markdown
    assert "社区热点" not in snippets[0].summary_markdown
    assert "This section should not enter item 49." not in snippets[0].summary_markdown
