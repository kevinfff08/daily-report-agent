"""Tests for DailyReport HTML rendering."""

from datetime import date
from pathlib import Path

from src.reporters.html_renderer import (
    render_existing_output_html,
    render_html_report,
    render_markdown_body,
)


def test_render_markdown_body_supports_report_constructs():
    markdown = """# Test Report

> From **10** items

## Section

### ⭐ [001] [Paper](https://example.com)

Inline math $p_q(o)=0$ and escaped tag `<end_plan>`.

$$
BSS(q) = 1 - \\sum_o p(o)^2
$$

```bash
python -m src.cli run
```

| 编号 | 标题 |
|------|------|
| [001] | [Paper](https://example.com) |
"""

    rendered = render_markdown_body(markdown)

    assert "highlight-heading" in rendered.body_html
    assert 'href="https://example.com"' in rendered.body_html
    assert '<span class="math-inline">$p_q(o)=0$</span>' in rendered.body_html
    assert '<div class="math-block">' in rendered.body_html
    assert "&lt;end_plan&gt;" in rendered.body_html
    assert "<table>" in rendered.body_html
    assert "<pre><code" in rendered.body_html


def test_render_html_report_is_standalone_and_skips_duplicate_title():
    html = render_html_report(
        "# 每日情报概览 — 2026-03-10\n\n## 论文\n\n内容",
        report_kind="overview",
        target_date=date(2026, 3, 10),
        source_filename="daily_report.md",
    )

    assert "<!DOCTYPE html>" in html
    assert "MathJax-script" in html
    assert "dailyreport-overview" in html
    assert html.count("每日情报概览") == 2  # title tag + visual header
    assert "daily_report.md" in html


def test_render_existing_output_html(tmp_path: Path):
    report_dir = tmp_path / "output" / "2026-03" / "2026-03-10"
    report_dir.mkdir(parents=True)
    (report_dir / "daily_report.md").write_text("# Daily\n\n## Section", encoding="utf-8")
    (report_dir / "deep_dive_report.md").write_text("# Deep\n\n$$\nx=1\n$$", encoding="utf-8")

    rendered = render_existing_output_html(tmp_path / "output", start_date=date(2026, 3, 10))

    assert len(rendered) == 2
    assert (report_dir / "daily_report.html").exists()
    assert (report_dir / "deep_dive_report.html").exists()
