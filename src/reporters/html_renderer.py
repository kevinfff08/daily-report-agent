"""Standalone HTML rendering for DailyReport markdown reports.

The renderer intentionally avoids extra runtime dependencies.  It supports the
markdown constructs produced by the report prompts: headings, paragraphs,
tables, lists, blockquotes, links, inline code, fenced code, and TeX math.
"""

from __future__ import annotations

import html
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
_INLINE_MATH_PATTERNS = [
    re.compile(r"\\\((.+?)\\\)"),
    re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$"),
]


@dataclass(frozen=True)
class Heading:
    """A rendered heading used to build the table of contents."""

    level: int
    text: str
    anchor: str


@dataclass(frozen=True)
class RenderedMarkdown:
    """Rendered markdown body plus extracted headings."""

    body_html: str
    headings: list[Heading]


def render_html_report(
    markdown: str,
    *,
    report_kind: ReportKind,
    target_date: date | None = None,
    source_filename: str | None = None,
) -> str:
    """Render a complete standalone HTML report from DailyReport markdown."""

    rendered = render_markdown_body(markdown, skip_first_h1=True)
    title = _extract_title(markdown) or _default_title(report_kind, target_date)
    report_label = "概览报告" if report_kind == "overview" else "深度分析报告"
    date_label = target_date.isoformat() if target_date else _extract_date_from_title(title)
    toc_html = _render_toc(rendered.headings)
    source_label = html.escape(source_filename or "Markdown report")

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
      <div class="kicker">DailyReport · {report_label}</div>
      <h1>{_render_inline(title)}</h1>
      <div class="report-meta">
        <span>{html.escape(date_label) if date_label else "日期未知"}</span>
        <span>HTML rendered from {source_label}</span>
        <span>MathJax enabled</span>
      </div>
    </header>
    <div class="report-layout">
      <main class="report-content" id="report-content">
{rendered.body_html}
      </main>
      {toc_html}
    </div>
  </div>
</body>
</html>
"""


def render_markdown_body(markdown: str, *, skip_first_h1: bool = False) -> RenderedMarkdown:
    """Render markdown body fragments used by DailyReport."""

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").split("\n")
    html_parts: list[str] = []
    headings: list[Heading] = []
    used_anchors: dict[str, int] = {}
    skipped_title = False
    i = 0

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
            anchor = _unique_anchor(_slugify(_plain_text(text)), used_anchors)
            headings.append(Heading(level=level, text=_plain_text(text), anchor=anchor))
            classes = ["heading", f"heading-{level}"]
            if "⭐" in text:
                classes.append("highlight-heading")
            class_attr = " ".join(classes)
            html_parts.append(
                f'<h{level} id="{anchor}" class="{class_attr}">{_render_inline(text)}</h{level}>'
            )
            i += 1
            continue

        if _is_horizontal_rule(stripped):
            html_parts.append("<hr>")
            i += 1
            continue

        if _is_table_start(lines, i):
            table, i = _render_table(lines, i)
            html_parts.append(table)
            continue

        if stripped.startswith(">"):
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

    return RenderedMarkdown(body_html="\n".join(html_parts), headings=headings)


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
    html_report = render_html_report(
        markdown,
        report_kind=report_kind,
        target_date=target_date,
        source_filename=source.name,
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


def _render_toc(headings: list[Heading]) -> str:
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


_REPORT_CSS = r"""
    :root {
      color-scheme: light;
      --page: #f5f7fa;
      --surface: #ffffff;
      --ink: #18202a;
      --muted: #637083;
      --soft: #eef2f6;
      --line: #d9e0e8;
      --line-strong: #b7c2cf;
      --accent: #156c75;
      --accent-strong: #0f4f72;
      --accent-soft: #e6f3f5;
      --highlight: #9b6500;
      --code-bg: #f2f5f8;
      --code-ink: #233244;
      --shadow: 0 18px 45px rgba(24, 32, 42, 0.08);
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
      font-family: ui-serif, "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", Georgia, serif;
      letter-spacing: 0;
    }

    .report-shell {
      width: min(1320px, 100%);
      margin: 0 auto;
      padding: 36px 24px 72px;
    }

    .report-header {
      padding: 12px 0 28px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 28px;
    }

    .kicker,
    .report-meta,
    .toc-title,
    table,
    code,
    pre {
      font-family: ui-sans-serif, "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    }

    .kicker {
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 12px;
    }

    .report-header h1 {
      margin: 0;
      max-width: 980px;
      font-size: 36px;
      line-height: 1.22;
      font-weight: 780;
      text-wrap: balance;
    }

    .report-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
    }

    .report-meta span {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.68);
    }

    .report-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 280px;
      gap: 36px;
      align-items: start;
    }

    .report-content {
      min-width: 0;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 44px 56px 56px;
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
      font-family: ui-sans-serif, "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      letter-spacing: 0;
      scroll-margin-top: 24px;
      text-wrap: balance;
    }

    .report-content h1 {
      margin: 36px 0 18px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line-strong);
      font-size: 28px;
      line-height: 1.28;
    }

    .report-content h2 {
      margin: 34px 0 14px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
      font-size: 23px;
      line-height: 1.32;
    }

    .report-content h3 {
      margin: 28px 0 10px;
      font-size: 18px;
      line-height: 1.42;
      color: var(--accent-strong);
    }

    .report-content h4 {
      margin: 24px 0 8px;
      font-size: 16px;
      line-height: 1.45;
      color: #2f3c4d;
    }

    .report-content .highlight-heading {
      color: var(--highlight);
    }

    .report-content p {
      margin: 0 0 16px;
      font-size: 16.5px;
      line-height: 1.86;
      text-wrap: pretty;
    }

    .report-content a {
      color: var(--accent-strong);
      text-decoration: underline;
      text-decoration-color: rgba(15, 79, 114, 0.35);
      text-underline-offset: 3px;
    }

    .report-content a:hover {
      color: var(--accent);
      text-decoration-color: currentColor;
    }

    .report-content strong {
      font-weight: 780;
    }

    blockquote {
      margin: 20px 0;
      padding: 14px 18px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--accent);
      border-radius: 6px;
      background: var(--accent-soft);
      color: #2c4050;
    }

    blockquote p {
      margin: 0;
      font-family: ui-sans-serif, "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
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
      font-size: 16px;
      line-height: 1.72;
    }

    hr {
      border: 0;
      border-top: 1px solid var(--line);
      margin: 32px 0;
    }

    .table-wrap {
      width: 100%;
      overflow-x: auto;
      margin: 20px 0 28px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 680px;
      font-size: 14px;
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
      background: #eef3f7;
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
      padding: 16px 18px;
      overflow-x: auto;
      border: 1px solid #d4dde7;
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
      padding: 14px 16px;
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      color: #172033;
      text-align: center;
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
      top: 24px;
      max-height: calc(100vh - 48px);
      overflow: auto;
      padding: 18px 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.86);
      box-shadow: 0 10px 26px rgba(24, 32, 42, 0.06);
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
      padding: 6px 0;
      color: #334155;
      font-family: ui-sans-serif, "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      font-size: 13px;
      line-height: 1.36;
      text-decoration: none;
      border-bottom: 1px solid transparent;
    }

    .toc-link:hover {
      color: var(--accent);
      border-bottom-color: var(--line);
    }

    .toc-level-2 {
      padding-left: 10px;
    }

    .toc-level-3 {
      padding-left: 22px;
      color: var(--muted);
      font-size: 12.5px;
    }

    @media (max-width: 1080px) {
      .report-layout {
        grid-template-columns: 1fr;
      }

      .report-toc {
        position: static;
        order: -1;
        max-height: none;
      }
    }

    @media (max-width: 760px) {
      .report-shell {
        padding: 22px 12px 48px;
      }

      .report-header h1 {
        font-size: 28px;
      }

      .report-content {
        padding: 28px 20px 36px;
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
        box-shadow: none;
        padding: 0;
      }

      a {
        color: inherit;
      }
    }
"""
