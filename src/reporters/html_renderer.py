"""Standalone HTML rendering for DailyReport markdown reports.

The renderer intentionally avoids extra runtime dependencies.  It supports the
markdown constructs produced by the report prompts: headings, paragraphs,
tables, lists, blockquotes, links, inline code, fenced code, and TeX math.
"""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

ReportKind = Literal["overview", "deep_dive"]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_RE = re.compile(r"^\s*(?P<marker>(?:[-*+])|(?:\d+[.)]))\s+(?P<text>.*)$")
_ORDERED_MARKER_RE = re.compile(r"^\d+[.)]$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_RAW_URL_ESCAPED_RE = re.compile(r'(?<!href=")(?<!>)(https?://[^\s<]+)')
_OVERVIEW_ITEM_HEADING_RE = re.compile(
    r"^(?P<star>⭐\s*)?\[(?P<index>\d{1,3})\]\s+(?P<title>.+)$"
)
_DEEP_SECTION_HEADING_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)\.\s+(?P<title>.+)$")
_INLINE_MATH_PATTERNS = [
    re.compile(r"\\\((.+?)\\\)"),
    re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$"),
]
_SOURCE_TYPE_CATEGORY = {
    "arxiv_paper": "论文",
    "semantic_scholar": "论文",
    "tavily_search": "业界动态",
    "product_hunt": "业界动态",
    "hacker_news": "社区热点",
    "youtube_video": "社区热点",
    "bilibili_video": "社区热点",
    "github_trending": "社区热点",
}
_TERMINAL_DEEP_SECTION_KEYWORDS = {
    "参考资料",
    "参考材料",
    "参考文献",
    "信息来源",
    "相关链接",
    "来源",
}


@dataclass(frozen=True)
class Heading:
    """A rendered heading used to build the table of contents."""

    level: int
    text: str
    anchor: str


@dataclass(frozen=True)
class DeepDiveItemMeta:
    """Metadata for one selected deep-dive item."""

    index: int
    title: str
    category: str
    source: str = ""
    url: str | None = None


@dataclass(frozen=True)
class TocGroup:
    """Grouped deep-dive table of contents for one selected item."""

    item: DeepDiveItemMeta
    headings: list[Heading]


@dataclass(frozen=True)
class RenderedMarkdown:
    """Rendered markdown body plus extracted headings."""

    body_html: str
    headings: list[Heading]
    item_groups: list[TocGroup]


def render_html_report(
    markdown: str,
    *,
    report_kind: ReportKind,
    target_date: date | None = None,
    source_filename: str | None = None,
    deep_dive_items: list[DeepDiveItemMeta] | None = None,
) -> str:
    """Render a complete standalone HTML report from DailyReport markdown."""

    rendered = render_markdown_body(
        markdown,
        skip_first_h1=True,
        report_kind=report_kind,
        deep_dive_items=deep_dive_items,
    )
    title = _extract_title(markdown) or _default_title(report_kind, target_date)
    report_label = "概览报告" if report_kind == "overview" else "深度分析报告"
    date_label = target_date.isoformat() if target_date else _extract_date_from_title(title)
    toc_html = _render_toc(rendered.headings, report_kind, rendered.item_groups)
    source_label = html.escape(source_filename or "Markdown report")
    header_summary = _render_header_summary(markdown, report_kind, deep_dive_items)
    section_chips = _render_section_chips(rendered.headings, report_kind, rendered.item_groups)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
{_REPORT_CSS}
  </style>
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
        processEscapes: true,
        tags: 'ams'
      }},
      options: {{
        skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
      }},
      chtml: {{
        scale: 1,
        minScale: 0.85,
        matchFontHeight: false
      }}
    }};
  </script>
  <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
</head>
<body class="dailyreport dailyreport-{report_kind}">
  <div class="report-shell">
    <header class="report-header">
      <div class="report-header-main">
        <div class="kicker">DailyReport · {report_label}</div>
        <h1>{_render_inline(title)}</h1>
        <div class="report-meta">
          <span>{html.escape(date_label) if date_label else "日期未知"}</span>
          <span>Source: {source_label}</span>
          <span>MathJax formulas</span>
        </div>
      </div>
      {header_summary}
      {section_chips}
    </header>
    <div class="report-layout">
      {toc_html}
      <main class="report-content" id="report-content">
{rendered.body_html}
      </main>
    </div>
  </div>
  <script>
{_COLLAPSE_SCRIPT}
  </script>
</body>
</html>
"""


def render_markdown_body(
    markdown: str,
    *,
    skip_first_h1: bool = False,
    report_kind: ReportKind = "overview",
    deep_dive_items: list[DeepDiveItemMeta] | None = None,
) -> RenderedMarkdown:
    """Render markdown body fragments used by DailyReport."""

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").split("\n")
    html_parts: list[str] = []
    headings: list[Heading] = []
    item_groups: list[TocGroup] = []
    used_anchors: dict[str, int] = {}
    skipped_title = False
    open_overview_item = False
    open_deep_section = False
    open_deep_section_lazy = False
    open_deep_item = False
    deep_items = deep_dive_items or []
    deep_item_cursor = -1
    deep_current_group: TocGroup | None = None
    deep_item_has_section = False
    deep_seen_terminal_section = False
    deep_section_count_for_item = 0
    i = 0

    def close_overview_item() -> None:
        nonlocal open_overview_item
        if open_overview_item:
            html_parts.append("</article>")
            open_overview_item = False

    def close_deep_section() -> None:
        nonlocal open_deep_section, open_deep_section_lazy
        if open_deep_section:
            html_parts.append("</template></section>" if open_deep_section_lazy else "</div></section>")
            open_deep_section = False
            open_deep_section_lazy = False

    def close_deep_item() -> None:
        nonlocal open_deep_item
        close_deep_section()
        if open_deep_item:
            html_parts.append("</div></article>")
            open_deep_item = False

    def open_next_deep_item() -> None:
        nonlocal deep_item_cursor, deep_current_group, deep_item_has_section
        nonlocal deep_seen_terminal_section, deep_section_count_for_item, open_deep_item
        deep_item_cursor += 1
        if deep_item_cursor < len(deep_items):
            item = deep_items[deep_item_cursor]
        else:
            item = DeepDiveItemMeta(
                index=deep_item_cursor + 1,
                title=f"Selected item {deep_item_cursor + 1}",
                category="Deep dive",
            )
        html_parts.append(_render_deep_item_open(item, open_by_default=deep_item_cursor == 0))
        deep_current_group = TocGroup(item=item, headings=[])
        item_groups.append(deep_current_group)
        deep_item_has_section = False
        deep_seen_terminal_section = False
        deep_section_count_for_item = 0
        open_deep_item = True

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            block, i = _render_code_block(lines, i)
            html_parts.append(block)
            continue

        if _is_math_block_start(stripped):
            block, i = _render_math_block(lines, i)
            html_parts.append(block)
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            if skip_first_h1 and level == 1 and not skipped_title:
                skipped_title = True
                i += 1
                continue
            if level <= 2:
                close_overview_item()
            anchor = _unique_anchor(_slugify(_plain_text(text)), used_anchors)
            heading = Heading(level=level, text=_plain_text(text), anchor=anchor)
            headings.append(heading)
            if report_kind == "deep_dive" and level == 1:
                if open_deep_item and _starts_next_deep_item(
                    heading.text,
                    deep_item_has_section=deep_item_has_section,
                    deep_seen_terminal_section=deep_seen_terminal_section,
                    current_item_index=deep_item_cursor,
                    total_items=max(len(deep_items), deep_item_cursor + 2),
                ):
                    close_deep_item()
                    open_next_deep_item()
                elif not open_deep_item:
                    open_next_deep_item()
                else:
                    close_deep_section()

                if deep_current_group is not None:
                    deep_current_group.headings.append(heading)
                open_by_default = deep_item_cursor == 0 and deep_section_count_for_item == 0
                html_parts.append(
                    _render_deep_section_open(
                        text,
                        anchor,
                        open_by_default=open_by_default,
                    )
                )
                deep_item_has_section = True
                deep_seen_terminal_section = _is_terminal_deep_section(heading.text)
                deep_section_count_for_item += 1
                open_deep_section = True
                open_deep_section_lazy = not open_by_default
                i += 1
                continue

            if report_kind == "deep_dive" and level in {2, 3} and not open_deep_item:
                open_next_deep_item()
            heading_html, opens_overview_item, opens_deep_section = _render_heading(
                level,
                text,
                anchor,
                report_kind,
            )
            if opens_overview_item:
                close_overview_item()
                open_overview_item = True
            if opens_deep_section:
                open_deep_section = True
            html_parts.append(heading_html)
            i += 1
            continue

        if _is_horizontal_rule(stripped):
            close_overview_item()
            if report_kind == "deep_dive":
                html_parts.append('<hr class="section-break">')
            else:
                html_parts.append("<hr>")
            i += 1
            continue

        if _is_table_start(lines, i):
            close_overview_item()
            table, i = _render_table(lines, i)
            html_parts.append(table)
            continue

        if stripped.startswith(">"):
            if report_kind == "deep_dive" and _is_selected_items_line(stripped.lstrip("> ").strip()):
                i += 1
                continue
            quote, i = _render_blockquote(lines, i)
            html_parts.append(quote)
            continue

        if _LIST_RE.match(line):
            list_html, i = _render_list(lines, i)
            html_parts.append(list_html)
            continue

        paragraph_lines: list[str] = []
        while i < len(lines):
            current = lines[i]
            current_stripped = current.strip()
            if not current_stripped or _is_block_start(lines, i):
                break
            paragraph_lines.append(current)
            i += 1
        html_parts.append(f"<p>{_render_paragraph(paragraph_lines)}</p>")

    close_overview_item()
    close_deep_item()
    return RenderedMarkdown(body_html="\n".join(html_parts), headings=headings, item_groups=item_groups)


def render_markdown_file(
    markdown_path: str | Path,
    html_path: str | Path,
    *,
    report_kind: ReportKind,
    target_date: date | None = None,
) -> Path:
    """Render one markdown report file to a standalone HTML file."""

    source = Path(markdown_path)
    destination = Path(html_path)
    markdown = source.read_text(encoding="utf-8")
    deep_dive_items = (
        _load_deep_dive_item_metadata(source, markdown, target_date)
        if report_kind == "deep_dive"
        else None
    )
    html_report = render_html_report(
        markdown,
        report_kind=report_kind,
        target_date=target_date,
        source_filename=source.name,
        deep_dive_items=deep_dive_items,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_report, encoding="utf-8")
    return destination


def render_existing_output_html(
    output_root: str | Path = "output",
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Path]:
    """Render HTML companions for existing output markdown reports."""

    root = Path(output_root)
    rendered: list[Path] = []
    for markdown_path in _iter_output_markdown_files(root):
        target_date = _date_from_report_path(markdown_path)
        if target_date is None or not _date_in_range(target_date, start_date, end_date):
            continue
        kind = _kind_from_filename(markdown_path.name)
        if kind is None:
            continue
        html_name = "daily_report.html" if kind == "overview" else "deep_dive_report.html"
        rendered.append(
            render_markdown_file(
                markdown_path,
                markdown_path.with_name(html_name),
                report_kind=kind,
                target_date=target_date,
            )
        )
    return rendered


def render_existing_data_report_html(
    data_root: str | Path = "data",
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Path]:
    """Render HTML companions for existing data/reports markdown files."""

    reports_root = Path(data_root) / "reports"
    rendered: list[Path] = []
    if not reports_root.exists():
        return rendered

    for markdown_path in sorted(reports_root.glob("*/*/*.md")):
        target_date = _date_from_report_path(markdown_path)
        if target_date is None or not _date_in_range(target_date, start_date, end_date):
            continue
        if markdown_path.name == "overview.md":
            rendered.append(
                render_markdown_file(
                    markdown_path,
                    markdown_path.with_name("overview.html"),
                    report_kind="overview",
                    target_date=target_date,
                )
            )
        elif markdown_path.name == "deep_dive.md":
            rendered.append(
                render_markdown_file(
                    markdown_path,
                    markdown_path.with_name("deep_dive.html"),
                    report_kind="deep_dive",
                    target_date=target_date,
                )
            )
    return rendered


def _load_deep_dive_item_metadata(
    source: Path,
    markdown: str,
    target_date: date | None,
) -> list[DeepDiveItemMeta]:
    selected_indices = _extract_selected_indices(markdown)
    if not selected_indices:
        return []

    selected_set = set(selected_indices)
    metadata_by_index: dict[int, DeepDiveItemMeta] = {}
    for index_path in _candidate_items_index_paths(source, target_date):
        metadata_by_index.update(_load_items_index_metadata(index_path, selected_set))
        if selected_set.issubset(metadata_by_index):
            break

    if not selected_set.issubset(metadata_by_index):
        for overview_path in _candidate_overview_paths(source, target_date):
            metadata_by_index.update(_load_overview_table_metadata(overview_path, selected_set))
            if selected_set.issubset(metadata_by_index):
                break

    return [
        metadata_by_index.get(
            index,
            DeepDiveItemMeta(index=index, title=f"Selected item {index:03d}", category="Deep dive"),
        )
        for index in selected_indices
    ]


def _candidate_items_index_paths(source: Path, target_date: date | None) -> list[Path]:
    candidates = [source.parent / "items_index.json"]
    if target_date is not None:
        month = target_date.strftime("%Y-%m")
        date_dir = target_date.isoformat()
        data_root = Path(os.environ.get("DATA_DIR", "data"))
        candidates.append(data_root / "reports" / month / date_dir / "items_index.json")
    return _unique_existing_candidates(candidates)


def _candidate_overview_paths(source: Path, target_date: date | None) -> list[Path]:
    candidates = [source.parent / "daily_report.md", source.parent / "overview.md"]
    if target_date is not None:
        month = target_date.strftime("%Y-%m")
        date_dir = target_date.isoformat()
        data_root = Path(os.environ.get("DATA_DIR", "data"))
        candidates.extend(
            [
                Path("output") / month / date_dir / "daily_report.md",
                data_root / "reports" / month / date_dir / "overview.md",
            ]
        )
    return _unique_existing_candidates(candidates)


def _unique_existing_candidates(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        normalized = path
        if normalized in seen or not normalized.exists():
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _load_items_index_metadata(
    path: Path,
    selected_indices: set[int],
) -> dict[int, DeepDiveItemMeta]:
    if not path.exists():
        return {}
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(entries, list):
        return {}

    metadata: dict[int, DeepDiveItemMeta] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        index = _coerce_int(entry.get("index"))
        if index is None or index not in selected_indices:
            continue
        source_item = entry.get("source_item")
        if not isinstance(source_item, dict):
            continue
        source_type = str(source_item.get("source_type") or "")
        source_metadata = source_item.get("metadata")
        if not isinstance(source_metadata, dict):
            source_metadata = {}
        title = str(source_item.get("title") or f"Selected item {index:03d}")
        source_name = str(
            source_metadata.get("source_name")
            or source_item.get("source_name")
            or _format_source_type(source_type)
        )
        metadata[index] = DeepDiveItemMeta(
            index=index,
            title=title,
            category=_SOURCE_TYPE_CATEGORY.get(source_type.lower(), _format_source_type(source_type)),
            source=source_name,
            url=str(source_item.get("url") or "") or None,
        )
    return metadata


def _load_overview_table_metadata(
    path: Path,
    selected_indices: set[int],
) -> dict[int, DeepDiveItemMeta]:
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    metadata: dict[int, DeepDiveItemMeta] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or "[" not in stripped:
            continue
        cells = _split_table_row(stripped)
        if len(cells) < 4:
            continue
        index_match = re.search(r"\[(\d{1,3})\]", cells[0])
        if not index_match:
            continue
        index = int(index_match.group(1))
        if index not in selected_indices:
            continue
        title_cell = cells[2]
        link_match = _LINK_RE.search(title_cell)
        metadata[index] = DeepDiveItemMeta(
            index=index,
            title=_plain_text(title_cell),
            category=_plain_text(cells[1]) or "Deep dive",
            source=_plain_text(cells[3]),
            url=link_match.group(2) if link_match else None,
        )
    return metadata


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _format_source_type(source_type: str) -> str:
    return source_type.replace("_", " ").strip().title() if source_type else "Unknown source"


def _render_header_summary(
    markdown: str,
    report_kind: ReportKind,
    deep_dive_items: list[DeepDiveItemMeta] | None = None,
) -> str:
    """Render report-aware metadata blocks in the page header."""

    if report_kind == "overview":
        raw_count, candidate_count = _extract_overview_counts(markdown)
        item_count = sum(
            1
            for line in markdown.splitlines()
            if _OVERVIEW_ITEM_HEADING_RE.match(line.strip().lstrip("#").strip())
        )
        stats = [
            ("原始数据", raw_count or "-"),
            ("候选条目", candidate_count or "-"),
            ("正文精选", str(item_count) if item_count else "-"),
        ]
        return _render_stat_strip(stats, "overview-stat-strip")

    selected = (
        ", ".join(f"[{item.index:03d}]" for item in deep_dive_items)
        if deep_dive_items
        else _extract_selected_items(markdown)
    )
    major_sections = len(re.findall(r"^#\s+\d+\.", markdown, flags=re.MULTILINE))
    formulas = len(re.findall(r"^\$\$", markdown, flags=re.MULTILINE)) // 2
    stats = [
        ("选中条目", selected or "-"),
        ("章节数量", str(major_sections) if major_sections else "-"),
        ("公式块", str(formulas) if formulas else "-"),
    ]
    return _render_stat_strip(stats, "deep-stat-strip")


def _render_stat_strip(stats: list[tuple[str, str]], class_name: str) -> str:
    items = "\n".join(
        f'<div class="stat"><span class="stat-label">{html.escape(label)}</span>'
        f'<strong>{html.escape(value)}</strong></div>'
        for label, value in stats
    )
    return f'<div class="report-stats {class_name}">{items}</div>'


def _render_section_chips(
    headings: list[Heading],
    report_kind: ReportKind,
    item_groups: list[TocGroup] | None = None,
) -> str:
    """Render a compact route map under the report title."""

    if report_kind == "overview":
        allowed = {"论文", "业界动态", "社区热点", "候选条目索引"}
        chips = [(heading.anchor, heading.text) for heading in headings if heading.text in allowed]
    else:
        chips = [
            (_deep_item_anchor(group.item), f"[{group.item.index:03d}] {group.item.title}")
            for group in (item_groups or [])
        ]

    if not chips:
        return ""

    label_limit = 22 if report_kind == "overview" else 42
    chip_html = "\n".join(
        f'<a href="#{anchor}">{html.escape(_shorten_text(label, label_limit))}</a>'
        for anchor, label in chips
    )
    return f'<nav class="section-chips" aria-label="报告结构">{chip_html}</nav>'


def _render_heading(
    level: int,
    text: str,
    anchor: str,
    report_kind: ReportKind,
) -> tuple[str, bool, bool]:
    """Render a report-aware heading.

    Returns:
        Tuple of (html, opens_overview_item, opens_deep_section).
    """

    if report_kind == "overview" and level == 3:
        match = _OVERVIEW_ITEM_HEADING_RE.match(text)
        if match:
            return _render_overview_item_heading(match, anchor), True, False

    if report_kind == "deep_dive" and level in {1, 2, 3}:
        return _render_deep_heading(level, text, anchor)

    classes = ["heading", f"heading-{level}"]
    plain_text = _plain_text(text)
    if plain_text in {"论文", "业界动态", "社区热点"}:
        classes.extend(["category-heading", f"category-{_slugify(plain_text)}"])
    if "今日要点" in plain_text:
        classes.append("insight-heading")
    if "候选条目索引" in plain_text:
        classes.append("index-heading")
    class_attr = " ".join(classes)
    return f'<h{level} id="{anchor}" class="{class_attr}">{_render_inline(text)}</h{level}>', False, False


def _render_overview_item_heading(match: re.Match[str], anchor: str) -> str:
    featured = bool(match.group("star"))
    index = match.group("index").zfill(3)
    title_markdown = match.group("title").strip()
    priority_label = "重点" if featured else "关注"
    classes = "brief-item brief-item-featured" if featured else "brief-item"
    return (
        f'<article class="{classes}">'
        f'<h3 id="{anchor}" class="heading heading-3 item-heading highlight-heading">'
        f'<span class="item-index">[{index}]</span>'
        f'<span class="item-title">{_render_inline(title_markdown)}</span>'
        f'<span class="item-priority">{priority_label}</span>'
        "</h3>"
    )


def _render_deep_heading(level: int, text: str, anchor: str) -> tuple[str, bool, bool]:
    match = _DEEP_SECTION_HEADING_RE.match(_plain_text(text))
    classes = ["heading", f"heading-{level}", "deep-heading"]
    if level == 1:
        classes.append("deep-major-heading")
    elif level == 2:
        classes.append("deep-sub-heading")
    else:
        classes.append("deep-minor-heading")

    class_attr = " ".join(classes)
    if match:
        number = match.group("number")
        title = text.split(".", 1)[1].strip() if "." in text else match.group("title")
        heading = (
            f'<h{level} id="{anchor}" class="{class_attr}">'
            f'<span class="section-number">{html.escape(number)}</span>'
            f'<span class="section-title">{_render_inline(title)}</span>'
            f'</h{level}>'
        )
    else:
        heading = f'<h{level} id="{anchor}" class="{class_attr}">{_render_inline(text)}</h{level}>'

    if level == 1:
        return f'<section class="analysis-section">{heading}', False, True
    return heading, False, False


def _render_deep_item_open(item: DeepDiveItemMeta, *, open_by_default: bool) -> str:
    open_class = " is-open" if open_by_default else ""
    expanded = "true" if open_by_default else "false"
    hidden_attr = "" if open_by_default else " hidden"
    body_id = _deep_item_body_id(item)
    source = item.source.strip() if item.source else ""
    meta_parts = [item.category]
    if source:
        meta_parts.append(source)
    link_html = ""
    if item.url:
        link_html = (
            f'<a class="deep-item-source-link" href="{html.escape(item.url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">source</a>'
        )
    return (
        f'<article class="deep-item{open_class}" id="{_deep_item_anchor(item)}">'
        '<div class="deep-item-header">'
        f'<button class="deep-item-toggle" type="button" data-collapse-toggle '
        f'aria-expanded="{expanded}" aria-controls="{body_id}">'
        f'<span class="deep-item-index">[{item.index:03d}]</span>'
        '<span class="deep-item-toggle-main">'
        f'<span class="deep-item-title">{html.escape(item.title)}</span>'
        f'<span class="deep-item-meta">{html.escape(" · ".join(meta_parts))}</span>'
        '</span>'
        '<span class="collapse-indicator" aria-hidden="true"></span>'
        '</button>'
        f'{link_html}'
        '</div>'
        f'<div class="deep-item-body" id="{body_id}"{hidden_attr}>'
    )


def _render_deep_section_open(
    text: str,
    anchor: str,
    *,
    open_by_default: bool,
) -> str:
    open_class = " is-open" if open_by_default else ""
    expanded = "true" if open_by_default else "false"
    body_id = _section_body_id(anchor)
    heading = _render_deep_section_toggle_heading(text, anchor, body_id, expanded)
    escaped_body_id = html.escape(body_id, quote=True)
    if not open_by_default:
        return (
            f'<section class="analysis-section{open_class}">'
            f"{heading}"
            f'<div class="analysis-body" id="{escaped_body_id}" hidden '
            f'data-lazy-panel="{escaped_body_id}">'
            '<div class="lazy-placeholder">展开后加载本节正文</div>'
            "</div>"
            f'<template data-lazy-template="{escaped_body_id}">'
        )
    return (
        f'<section class="analysis-section{open_class}">'
        f"{heading}"
        f'<div class="analysis-body" id="{escaped_body_id}">'
    )


def _render_deep_section_toggle_heading(
    text: str,
    anchor: str,
    body_id: str,
    expanded: str,
) -> str:
    match = _DEEP_SECTION_HEADING_RE.match(_plain_text(text))
    classes = "heading heading-1 deep-heading deep-major-heading"
    if match:
        number = match.group("number")
        title = text.split(".", 1)[1].strip() if "." in text else match.group("title")
        return (
            f'<h1 id="{anchor}" class="{classes}">'
            f'<button class="analysis-toggle" type="button" data-collapse-toggle '
            f'aria-expanded="{expanded}" aria-controls="{body_id}">'
            f'<span class="section-number">{html.escape(number)}</span>'
            f'<span class="section-title">{_render_inline(title)}</span>'
            '<span class="collapse-indicator" aria-hidden="true"></span>'
            '</button>'
            "</h1>"
        )
    return (
        f'<h1 id="{anchor}" class="{classes}">'
        f'<button class="analysis-toggle" type="button" data-collapse-toggle '
        f'aria-expanded="{expanded}" aria-controls="{body_id}">'
        f'<span class="section-title">{_render_inline(text)}</span>'
        '<span class="collapse-indicator" aria-hidden="true"></span>'
        '</button>'
        "</h1>"
    )


def _starts_next_deep_item(
    heading_text: str,
    *,
    deep_item_has_section: bool,
    deep_seen_terminal_section: bool,
    current_item_index: int,
    total_items: int,
) -> bool:
    if not deep_item_has_section or current_item_index + 1 >= total_items:
        return False
    if deep_seen_terminal_section:
        return True
    return bool(re.match(r"^1(?:\.|\s)", heading_text.strip()))


def _is_terminal_deep_section(heading_text: str) -> bool:
    label = _strip_heading_number(heading_text)
    return any(keyword in label for keyword in _TERMINAL_DEEP_SECTION_KEYWORDS)


def _deep_item_anchor(item: DeepDiveItemMeta) -> str:
    return f"item-{item.index:03d}"


def _deep_item_body_id(item: DeepDiveItemMeta) -> str:
    return f"{_deep_item_anchor(item)}-body"


def _section_body_id(anchor: str) -> str:
    return f"{anchor}-body"


def _render_code_block(lines: list[str], start: int) -> tuple[str, int]:
    fence_line = lines[start].strip()
    language = fence_line[3:].strip().split(maxsplit=1)[0] if len(fence_line) > 3 else ""
    code_lines: list[str] = []
    i = start + 1
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            i += 1
            break
        code_lines.append(lines[i])
        i += 1
    language_class = f' class="language-{html.escape(language)}"' if language else ""
    code = html.escape("\n".join(code_lines))
    return f"<pre><code{language_class}>{code}</code></pre>", i


def _render_math_block(lines: list[str], start: int) -> tuple[str, int]:
    first = lines[start].strip()
    math_lines = [lines[start]]
    i = start + 1
    if first != "$$" and first.endswith("$$") and len(first) > 2:
        i = start + 1
    else:
        while i < len(lines):
            math_lines.append(lines[i])
            if lines[i].strip().endswith("$$"):
                i += 1
                break
            i += 1
    math_text = html.escape("\n".join(math_lines))
    return f'<div class="math-block">{math_text}</div>', i


def _render_table(lines: list[str], start: int) -> tuple[str, int]:
    rows: list[list[str]] = []
    i = start
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        if i != start + 1:
            rows.append(_split_table_row(lines[i]))
        i += 1

    if not rows:
        return "", i

    header = rows[0]
    body_rows = rows[1:]
    header_html = "".join(f"<th>{_render_inline(cell)}</th>" for cell in header)
    body_html = "\n".join(
        "<tr>" + "".join(f"<td>{_render_inline(cell)}</td>" for cell in row) + "</tr>"
        for row in body_rows
    )
    table_html = (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table></div>"
    )
    return table_html, i


def _render_blockquote(lines: list[str], start: int) -> tuple[str, int]:
    quote_lines: list[str] = []
    i = start
    while i < len(lines) and lines[i].strip().startswith(">"):
        quote_lines.append(lines[i].strip()[1:].lstrip())
        i += 1
    return f"<blockquote><p>{_render_paragraph(quote_lines)}</p></blockquote>", i


def _render_list(lines: list[str], start: int) -> tuple[str, int]:
    first_match = _LIST_RE.match(lines[start])
    if first_match is None:
        return "", start + 1

    ordered = bool(_ORDERED_MARKER_RE.match(first_match.group("marker")))
    tag = "ol" if ordered else "ul"
    items: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        match = _LIST_RE.match(line)
        if match:
            marker_is_ordered = bool(_ORDERED_MARKER_RE.match(match.group("marker")))
            if marker_is_ordered != ordered:
                break
            items.append(_render_inline(match.group("text").strip()))
            i += 1
            continue
        if line.strip() and items and line.startswith((" ", "\t")):
            items[-1] += "<br>" + _render_inline(line.strip())
            i += 1
            continue
        break

    items_html = "\n".join(f"<li>{item}</li>" for item in items)
    return f"<{tag}>{items_html}</{tag}>", i


def _render_paragraph(lines: list[str]) -> str:
    rendered_parts: list[str] = []
    for line in lines:
        hard_break = line.endswith("  ")
        rendered_parts.append(_render_inline(line.rstrip()))
        rendered_parts.append("<br>" if hard_break else " ")
    return "".join(rendered_parts).strip()


def _render_inline(text: str) -> str:
    placeholders: dict[str, str] = {}

    def stash(value: str) -> str:
        key = f"@@DR_PLACEHOLDER_{len(placeholders)}@@"
        placeholders[key] = value
        return key

    def code_repl(match: re.Match[str]) -> str:
        return stash(f"<code>{html.escape(match.group(1))}</code>")

    def math_repl(match: re.Match[str]) -> str:
        return stash(f'<span class="math-inline">{html.escape(match.group(0))}</span>')

    protected = _CODE_SPAN_RE.sub(code_repl, text)
    for pattern in _INLINE_MATH_PATTERNS:
        protected = pattern.sub(math_repl, protected)

    escaped = html.escape(protected)
    escaped = _IMAGE_RE.sub(_image_repl, escaped)
    escaped = _LINK_RE.sub(_link_repl, escaped)
    escaped = _RAW_URL_ESCAPED_RE.sub(_raw_url_repl, escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"~~(.+?)~~", r"<del>\1</del>", escaped)

    for key, value in placeholders.items():
        escaped = escaped.replace(html.escape(key), value)
    return escaped


def _link_repl(match: re.Match[str]) -> str:
    label = match.group(1)
    url = html.escape(match.group(2), quote=True)
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'


def _image_repl(match: re.Match[str]) -> str:
    alt = html.escape(match.group(1), quote=True)
    url = html.escape(match.group(2), quote=True)
    return f'<img src="{url}" alt="{alt}" loading="lazy">'


def _raw_url_repl(match: re.Match[str]) -> str:
    url = match.group(1)
    trailing = ""
    while url and url[-1] in ".,;，。；）)]":
        trailing = url[-1] + trailing
        url = url[:-1]
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>{trailing}'


def _render_toc(
    headings: list[Heading],
    report_kind: ReportKind,
    item_groups: list[TocGroup],
) -> str:
    if report_kind == "deep_dive" and item_groups:
        groups_html = "\n".join(_render_deep_toc_group(group) for group in item_groups)
        return f"""<aside class="report-toc report-toc-deep" aria-label="选中条目目录">
        <div class="toc-title">选中条目</div>
        <nav>{groups_html}</nav>
      </aside>"""

    toc_headings = [heading for heading in headings if heading.level <= 3]
    if len(toc_headings) < 2:
        return ""

    links = "\n".join(
        (
            f'<a class="toc-link toc-level-{heading.level}" href="#{heading.anchor}">'
            f"{html.escape(heading.text)}</a>"
        )
        for heading in toc_headings
    )
    return f"""<aside class="report-toc" aria-label="目录">
        <div class="toc-title">目录</div>
        <nav>{links}</nav>
      </aside>"""


def _render_deep_toc_group(group: TocGroup) -> str:
    item = group.item
    sections = "\n".join(
        f'<a class="toc-link toc-level-1" href="#{heading.anchor}">'
        f"{html.escape(_shorten_text(_strip_heading_number(heading.text), 34))}</a>"
        for heading in group.headings
    )
    category = f"<span>{html.escape(item.category)}</span>"
    source = f"<span>{html.escape(item.source)}</span>" if item.source else ""
    return (
        '<div class="toc-item-group">'
        f'<a class="toc-item-card" href="#{_deep_item_anchor(item)}">'
        f'<span class="toc-item-index">[{item.index:03d}]</span>'
        '<span class="toc-item-main">'
        f'<strong>{html.escape(_shorten_text(item.title, 58))}</strong>'
        f"<em>{category}{source}</em>"
        '</span>'
        '</a>'
        f'<div class="toc-sections">{sections}</div>'
        '</div>'
    )


def _is_block_start(lines: list[str], index: int) -> bool:
    stripped = lines[index].strip()
    return (
        stripped.startswith("```")
        or _is_math_block_start(stripped)
        or bool(_HEADING_RE.match(lines[index]))
        or _is_horizontal_rule(stripped)
        or _is_table_start(lines, index)
        or stripped.startswith(">")
        or bool(_LIST_RE.match(lines[index]))
    )


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return "|" in lines[index] and bool(_TABLE_SEPARATOR_RE.match(lines[index + 1]))


def _is_horizontal_rule(stripped: str) -> bool:
    return bool(re.fullmatch(r"[-*_]\s*[-*_]\s*[-*_][\s\-*_]*", stripped))


def _is_math_block_start(stripped: str) -> bool:
    return stripped.startswith("$$")


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _plain_text(markdown: str) -> str:
    text = _LINK_RE.sub(r"\1", markdown)
    text = _IMAGE_RE.sub(r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[*_~#]+", "", text)
    return html.unescape(text).strip()


def _extract_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return _plain_text(match.group(2))
    return None


def _extract_date_from_title(title: str) -> str | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", title)
    return match.group(0) if match else None


def _extract_overview_counts(markdown: str) -> tuple[str | None, str | None]:
    match = re.search(r"从\s+\*\*(\d+)\*\*.*?候选\s+\*\*(\d+)\*\*", markdown, flags=re.DOTALL)
    if match:
        return match.group(1), match.group(2)
    return None, None


def _extract_selected_items(markdown: str) -> str | None:
    match = re.search(r"选中条目:\s*([^\n]+)", markdown)
    if not match:
        return None
    return html.unescape(_plain_text(match.group(1))).strip()


def _extract_selected_indices(markdown: str) -> list[int]:
    for line in markdown.splitlines():
        if not _is_selected_items_line(line):
            continue
        return [int(value) for value in re.findall(r"\[(\d{1,3})\]", line)]
    return []


def _is_selected_items_line(line: str) -> bool:
    return "选中条目" in line or "閫変腑" in line or "Selected" in line


def _shorten_text(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def _strip_heading_number(text: str) -> str:
    return _DEEP_SECTION_HEADING_RE.sub(r"\g<title>", text).strip()


def _default_title(report_kind: ReportKind, target_date: date | None) -> str:
    label = "每日情报概览" if report_kind == "overview" else "深度分析报告"
    return f"{label} — {target_date.isoformat()}" if target_date else label


def _slugify(text: str) -> str:
    normalized = re.sub(r"\s+", "-", text.lower()).strip("-")
    slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", normalized)
    return slug or "section"


def _unique_anchor(anchor: str, used: dict[str, int]) -> str:
    count = used.get(anchor, 0)
    used[anchor] = count + 1
    return anchor if count == 0 else f"{anchor}-{count + 1}"


def _iter_output_markdown_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    markdown_files = [
        *root.glob("*/*/daily_report.md"),
        *root.glob("*/*/deep_dive_report.md"),
    ]
    return sorted(markdown_files)


def _date_from_report_path(path: Path) -> date | None:
    for part in reversed(path.parts):
        try:
            return date.fromisoformat(part)
        except ValueError:
            continue
    return None


def _kind_from_filename(filename: str) -> ReportKind | None:
    if filename in {"daily_report.md", "overview.md"}:
        return "overview"
    if filename in {"deep_dive_report.md", "deep_dive.md"}:
        return "deep_dive"
    return None


def _date_in_range(value: date, start: date | None, end: date | None) -> bool:
    if start and value < start:
        return False
    if end and value > end:
        return False
    return True


_COLLAPSE_SCRIPT = r"""
    function hydrateLazyPanel(panel) {
      const key = panel.dataset.lazyPanel;
      if (!key || panel.dataset.lazyLoaded === 'true') {
        return;
      }
      const template = Array.from(document.querySelectorAll('template[data-lazy-template]'))
        .find((item) => item.dataset.lazyTemplate === key);
      if (!template) {
        return;
      }
      panel.replaceChildren(template.content.cloneNode(true));
      panel.dataset.lazyLoaded = 'true';
      template.remove();
    }

    function typesetPanel(panel) {
      if (!window.MathJax || !window.MathJax.typesetPromise) {
        return;
      }
      window.MathJax.typesetPromise([panel]).catch(() => {});
    }

    document.addEventListener('click', function (event) {
      const toggle = event.target.closest('[data-collapse-toggle]');
      if (!toggle) {
        return;
      }
      const panel = document.getElementById(toggle.getAttribute('aria-controls'));
      if (!panel) {
        return;
      }
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      if (!expanded) {
        hydrateLazyPanel(panel);
      }
      toggle.setAttribute('aria-expanded', String(!expanded));
      panel.hidden = expanded;
      const container = toggle.closest('.deep-item, .analysis-section');
      if (container) {
        container.classList.toggle('is-open', !expanded);
      }
      if (!expanded) {
        typesetPanel(panel);
      }
    });

    document.addEventListener('keydown', function (event) {
      if ((event.key !== 'Enter' && event.key !== ' ') || !event.target.matches('[data-collapse-toggle]')) {
        return;
      }
      event.preventDefault();
      event.target.click();
    });
"""


_REPORT_CSS = r"""
    :root {
      color-scheme: light;
      --page: #eef1f4;
      --paper: #fffdf8;
      --paper-soft: #fbfaf6;
      --ink: #171b24;
      --body: #27303d;
      --muted: #687282;
      --line: #d9dee6;
      --line-strong: #b8c0cc;
      --blue: #174d7a;
      --teal: #1d6f73;
      --green: #2f6b4f;
      --amber: #8a5a00;
      --amber-soft: #fff4d9;
      --violet: #5b537d;
      --code-bg: #eef2f7;
      --code-ink: #1e293b;
      --shadow: 0 16px 34px rgba(28, 35, 47, 0.08);
    }

    * {
      box-sizing: border-box;
    }

    html {
      scroll-behavior: smooth;
    }

    body {
      margin: 0;
      background: var(--page);
      color: var(--ink);
      font-family: "Iowan Old Style", "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", Georgia, serif;
      letter-spacing: 0;
    }

    .report-shell {
      width: min(1440px, 100%);
      margin: 0 auto;
      padding: 28px 28px 80px;
    }

    .report-header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, 360px);
      gap: 24px;
      align-items: end;
      padding: 30px 0 24px;
      border-bottom: 2px solid #202635;
      margin-bottom: 24px;
    }

    .report-header-main {
      min-width: 0;
    }

    .kicker,
    .report-meta,
    .toc-title,
    .section-chips,
    .stat,
    .item-heading,
    .report-toc,
    table,
    code,
    pre {
      font-family: "Aptos", "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    }

    .kicker {
      color: var(--teal);
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 12px;
    }

    .report-header h1 {
      margin: 0;
      max-width: 1040px;
      font-size: 42px;
      line-height: 1.14;
      font-weight: 760;
      text-wrap: balance;
    }

    .report-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
      color: var(--muted);
      font-size: 12.5px;
    }

    .report-meta span {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 9px;
      border: 1px solid var(--line);
      border-radius: 5px;
      background: rgba(255, 253, 248, 0.76);
    }

    .report-stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1px;
      overflow: hidden;
      align-self: stretch;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: var(--line-strong);
    }

    .stat {
      min-width: 0;
      padding: 14px 16px 13px;
      background: var(--paper);
    }

    .stat-label {
      display: block;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }

    .stat strong {
      display: block;
      color: var(--ink);
      font-size: 22px;
      line-height: 1.1;
      font-weight: 760;
      overflow-wrap: anywhere;
    }

    .section-chips {
      grid-column: 1 / -1;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding-top: 2px;
    }

    .section-chips a {
      min-height: 30px;
      padding: 6px 11px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255, 253, 248, 0.78);
      color: #344154;
      font-size: 13px;
      font-weight: 650;
      line-height: 1.25;
      text-decoration: none;
    }

    .section-chips a:hover {
      border-color: var(--blue);
      color: var(--blue);
    }

    .report-layout {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 30px;
      align-items: start;
    }

    .report-content {
      min-width: 0;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 44px 60px 60px;
    }

    .report-content > :first-child {
      margin-top: 0;
    }

    .report-content h1,
    .report-content h2,
    .report-content h3,
    .report-content h4,
    .report-content h5,
    .report-content h6 {
      color: var(--ink);
      font-family: "Aptos Display", "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      letter-spacing: 0;
      scroll-margin-top: 24px;
      text-wrap: balance;
    }

    .report-content h1 {
      margin: 36px 0 18px;
      padding-bottom: 12px;
      border-bottom: 2px solid #222938;
      font-size: 30px;
      line-height: 1.28;
    }

    .report-content h2 {
      margin: 44px 0 16px;
      font-size: 25px;
      line-height: 1.25;
    }

    .report-content h3 {
      margin: 26px 0 10px;
      font-size: 18px;
      line-height: 1.42;
      color: var(--blue);
    }

    .report-content h4 {
      margin: 24px 0 8px;
      font-size: 16px;
      line-height: 1.45;
      color: #2f3c4d;
    }

    .category-heading {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 48px;
      padding: 12px 0 10px;
      border-top: 3px solid #202635;
      border-bottom: 1px solid var(--line);
      color: #202635;
      font-size: 28px;
    }

    .category-heading::before {
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--teal);
    }

    .category-业界动态::before {
      background: var(--amber);
    }

    .category-社区热点::before {
      background: var(--violet);
    }

    .insight-heading {
      margin-top: 18px;
      padding: 0 0 0 14px;
      border-left: 4px solid var(--teal);
      color: #253041;
      font-size: 20px;
    }

    .index-heading {
      margin-top: 54px;
      padding-top: 22px;
      border-top: 3px double var(--line-strong);
    }

    .report-content p {
      margin: 0 0 16px;
      color: var(--body);
      font-size: 17px;
      line-height: 1.92;
      text-wrap: pretty;
    }

    .report-content a {
      color: var(--blue);
      text-decoration: underline;
      text-decoration-color: rgba(23, 77, 122, 0.32);
      text-underline-offset: 3px;
    }

    .report-content a:hover {
      color: var(--teal);
      text-decoration-color: currentColor;
    }

    .report-content strong {
      font-weight: 780;
    }

    .brief-item {
      margin: 18px 0;
      padding: 18px 20px 2px;
      border: 1px solid var(--line);
      border-left: 5px solid #8a96a8;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 8px 20px rgba(27, 34, 45, 0.045);
    }

    .brief-item-featured {
      border-left-color: var(--amber);
      background: #fffdfa;
    }

    .item-heading {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      margin: 0 0 10px !important;
      color: var(--ink) !important;
      font-size: 17px !important;
      line-height: 1.35 !important;
    }

    .item-index {
      display: inline-flex;
      align-items: center;
      min-height: 25px;
      padding: 2px 7px;
      border-radius: 5px;
      background: #edf1f5;
      color: #334155;
      font-size: 12px;
      font-weight: 760;
      white-space: nowrap;
    }

    .brief-item-featured .item-index {
      background: var(--amber-soft);
      color: var(--amber);
    }

    .item-title {
      min-width: 0;
    }

    .item-priority {
      padding: 3px 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .brief-item-featured .item-priority {
      border-color: #edca79;
      background: var(--amber-soft);
      color: var(--amber);
    }

    .brief-item p {
      margin-bottom: 13px;
      font-size: 16px;
      line-height: 1.78;
    }

    .dailyreport-deep .report-content {
      padding: 28px 34px 42px;
      background: #f9faf8;
    }

    .deep-item {
      margin: 0 0 22px;
      overflow: hidden;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: var(--paper);
      box-shadow: 0 12px 26px rgba(27, 34, 45, 0.055);
    }

    .deep-item-header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 13px;
      background: #ffffff;
      border-bottom: 1px solid transparent;
    }

    .deep-item.is-open > .deep-item-header {
      border-bottom-color: var(--line);
      background: #fbfcfd;
    }

    .deep-item-toggle,
    .analysis-toggle {
      width: 100%;
      border: 0;
      color: inherit;
      background: transparent;
      text-align: left;
      cursor: pointer;
      font-family: "Aptos", "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    }

    .deep-item-toggle {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 13px;
      align-items: start;
      min-height: 68px;
      padding: 16px 18px;
    }

    .deep-item-toggle:hover,
    .analysis-toggle:hover {
      background: #f3f6f9;
    }

    .deep-item-toggle:focus-visible,
    .analysis-toggle:focus-visible {
      outline: 2px solid var(--blue);
      outline-offset: -2px;
    }

    .collapse-indicator {
      width: 9px;
      height: 9px;
      margin-top: 8px;
      border-right: 2px solid var(--muted);
      border-bottom: 2px solid var(--muted);
      transform: rotate(45deg);
      transition: transform 160ms ease, border-color 160ms ease;
    }

    .deep-item.is-open > .deep-item-header .collapse-indicator,
    .analysis-section.is-open .collapse-indicator {
      transform: rotate(225deg);
      border-color: var(--blue);
    }

    .deep-item-index {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 8px;
      border-radius: 5px;
      background: #202635;
      color: #ffffff;
      font-size: 12px;
      font-weight: 780;
      line-height: 1;
      white-space: nowrap;
    }

    .deep-item-toggle-main {
      display: grid;
      gap: 5px;
      min-width: 0;
    }

    .deep-item-title {
      color: var(--ink);
      font-size: 18px;
      font-weight: 760;
      line-height: 1.35;
      text-wrap: pretty;
    }

    .deep-item-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      align-items: center;
      color: var(--muted);
      font-size: 12.5px;
      font-weight: 650;
    }

    .deep-item-source-link {
      align-self: center;
      margin-right: 16px;
      padding: 5px 8px;
      border: 1px solid var(--line);
      border-radius: 5px;
      color: var(--blue);
      text-decoration: none;
      font-family: "Aptos", "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .deep-item-body {
      padding: 18px 18px 22px;
    }

    .analysis-section {
      margin: 0 0 14px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }

    .analysis-body {
      padding: 4px 22px 22px;
      border-top: 1px solid var(--line);
      background: var(--paper);
    }

    .lazy-placeholder {
      padding: 18px 0;
      color: var(--muted);
      font-size: 13px;
    }

    .analysis-body > :last-child {
      margin-bottom: 0;
    }

    .deep-major-heading {
      margin: 0 !important;
      padding: 0 !important;
      border: 0 !important;
      font-size: 22px !important;
    }

    .analysis-toggle {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 14px;
      align-items: center;
      padding: 17px 16px;
    }

    .deep-sub-heading {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      margin: 32px 0 12px !important;
      color: var(--teal) !important;
      font-size: 21px !important;
    }

    .deep-minor-heading {
      margin-top: 24px !important;
      color: var(--green) !important;
    }

    .section-number {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 38px;
      height: 34px;
      padding: 0 8px;
      border: 1px solid #202635;
      border-radius: 6px;
      background: #202635;
      color: #ffffff;
      font-size: 15px;
      font-weight: 760;
      line-height: 1;
    }

    .deep-sub-heading .section-number {
      min-width: 32px;
      height: 28px;
      border-color: #c7d7d7;
      background: #eaf3f2;
      color: var(--teal);
      font-size: 12px;
    }

    .section-title {
      min-width: 0;
    }

    blockquote {
      margin: 20px 0;
      padding: 15px 18px;
      border: 1px solid var(--line);
      border-left: 5px solid var(--blue);
      border-radius: 8px;
      background: #f4f7fb;
      color: #2c4050;
    }

    blockquote p {
      margin: 0;
      font-family: "Aptos", "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      font-size: 14.5px;
      line-height: 1.65;
    }

    ul,
    ol {
      margin: 0 0 18px 1.25rem;
      padding: 0;
    }

    li {
      margin: 7px 0;
      padding-left: 4px;
      color: var(--body);
      font-size: 16px;
      line-height: 1.75;
    }

    hr {
      border: 0;
      border-top: 1px solid var(--line);
      margin: 32px 0;
    }

    .section-break {
      margin: 30px 0;
      border-top-color: var(--line-strong);
    }

    .table-wrap {
      width: 100%;
      overflow-x: auto;
      margin: 20px 0 28px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      box-shadow: var(--shadow);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 680px;
      font-size: 13.5px;
      line-height: 1.55;
    }

    th,
    td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
    }

    th {
      position: sticky;
      top: 0;
      background: #eef1f5;
      color: #334155;
      font-weight: 740;
      white-space: nowrap;
    }

    tr:last-child td {
      border-bottom: 0;
    }

    tr:nth-child(even) td {
      background: #fafbfd;
    }

    code {
      padding: 0.12rem 0.32rem;
      border: 1px solid #d8e1ea;
      border-radius: 5px;
      background: var(--code-bg);
      color: var(--code-ink);
      font-size: 0.9em;
    }

    pre {
      margin: 18px 0 24px;
      padding: 18px 20px;
      overflow-x: auto;
      border: 1px solid #2b3545;
      border-radius: 8px;
      background: #111827;
      color: #e5edf6;
      line-height: 1.6;
    }

    pre code {
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
      color: inherit;
      font-size: 13.5px;
    }

    .math-block {
      margin: 20px 0 26px;
      padding: 18px 18px;
      overflow-x: auto;
      border: 1px solid #cfd7e2;
      border-radius: 8px;
      background: #ffffff;
      color: #172033;
      text-align: center;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7);
    }

    .math-inline {
      white-space: nowrap;
    }

    img {
      max-width: 100%;
      height: auto;
      border-radius: 6px;
    }

    .report-toc {
      position: sticky;
      top: 22px;
      max-height: calc(100vh - 48px);
      overflow: auto;
      padding: 18px 0;
      border-top: 2px solid #202635;
      border-bottom: 1px solid var(--line-strong);
      background: transparent;
    }

    .toc-title {
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 780;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .toc-link {
      display: block;
      padding: 7px 0 7px 12px;
      border-left: 2px solid transparent;
      color: #334155;
      font-size: 13px;
      line-height: 1.36;
      text-decoration: none;
    }

    .toc-link:hover {
      color: var(--blue);
      border-left-color: var(--blue);
      background: rgba(255, 253, 248, 0.58);
    }

    .toc-level-2 {
      padding-left: 22px;
    }

    .toc-level-3 {
      padding-left: 34px;
      color: var(--muted);
      font-size: 12.5px;
    }

    .report-toc-deep {
      padding-top: 14px;
    }

    .toc-item-group {
      margin: 0 0 14px;
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(184, 192, 204, 0.72);
    }

    .toc-item-card {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 9px;
      align-items: start;
      padding: 9px 9px 10px;
      border: 1px solid transparent;
      border-radius: 8px;
      color: var(--ink);
      text-decoration: none;
    }

    .toc-item-card:hover {
      border-color: var(--line-strong);
      background: rgba(255, 253, 248, 0.82);
    }

    .toc-item-index {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 3px 6px;
      border-radius: 5px;
      background: #202635;
      color: #ffffff;
      font-size: 11px;
      font-weight: 760;
      line-height: 1;
      white-space: nowrap;
    }

    .toc-item-main {
      display: grid;
      gap: 4px;
      min-width: 0;
    }

    .toc-item-main strong {
      color: var(--ink);
      font-size: 13px;
      line-height: 1.32;
      font-weight: 760;
      text-wrap: pretty;
    }

    .toc-item-main em {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      color: var(--muted);
      font-size: 11.5px;
      line-height: 1.25;
      font-style: normal;
      font-weight: 650;
    }

    .toc-sections {
      margin-top: 4px;
      padding-left: 12px;
    }

    .toc-sections .toc-link {
      padding: 5px 0 5px 12px;
      color: #4f5b6d;
      font-size: 12.5px;
    }

    @media (max-width: 1080px) {
      .report-header {
        grid-template-columns: 1fr;
      }

      .report-layout {
        grid-template-columns: 1fr;
      }

      .report-toc {
        position: static;
        order: -1;
        max-height: none;
        padding: 14px 0;
      }
    }

    @media (max-width: 760px) {
      .report-shell {
        padding: 20px 12px 48px;
      }

      .report-header h1 {
        font-size: 30px;
      }

      .report-stats {
        grid-template-columns: 1fr;
      }

      .report-content {
        padding: 28px 18px 38px;
      }

      .dailyreport-deep .report-content {
        padding: 16px 10px 30px;
      }

      .report-content h1 {
        font-size: 24px;
      }

      .report-content h2 {
        font-size: 20px;
      }

      .report-content p,
      li {
        font-size: 15.5px;
      }

      .item-heading {
        grid-template-columns: 1fr;
      }

      .item-index,
      .item-priority {
        width: fit-content;
      }

      .deep-major-heading,
      .deep-sub-heading {
        grid-template-columns: 1fr;
      }

      .deep-item-index {
        width: fit-content;
      }

      .analysis-toggle {
        padding: 15px 12px;
      }

      .analysis-body {
        padding: 4px 14px 18px;
      }
    }

    @media print {
      body {
        background: #ffffff;
      }

      .report-shell {
        width: 100%;
        padding: 0;
      }

      .report-toc {
        display: none;
      }

      .report-layout {
        display: block;
      }

      .report-content {
        border: 0;
        padding: 0;
      }

      .brief-item,
      .table-wrap {
        box-shadow: none;
      }

      a {
        color: inherit;
      }
    }
"""
