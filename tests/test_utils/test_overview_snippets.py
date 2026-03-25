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
