"""Standalone HTML rendering for the monthly deep-dive registry."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from src.models.registry import InterestStatus, RegistryEntry
from src.reporters.html_renderer import render_markdown_body

_STATUS_DEFS = [
    (InterestStatus.STAR, "star", "非常关注"),
    (InterestStatus.QUESTION, "question", "需要学习"),
    (InterestStatus.CHECK, "check", "可能有用"),
]


def render_registry_month_file(
    markdown_path: str | Path,
    entries: list[RegistryEntry],
) -> Path:
    """Render an HTML companion next to one monthly registry Markdown file."""

    source = Path(markdown_path)
    year_month = source.name.removesuffix("-record.md")
    destination = source.with_suffix(".html")
    destination.write_text(
        render_registry_month_html(
            entries,
            year_month=year_month,
            source_filename=source.name,
            source_markdown=source.read_text(encoding="utf-8") if source.exists() else "",
        ),
        encoding="utf-8",
    )
    return destination


def render_registry_month_html(
    entries: list[RegistryEntry],
    *,
    year_month: str,
    source_filename: str,
    source_markdown: str = "",
) -> str:
    """Render a standalone HTML registry for one month."""

    sorted_entries = sorted(entries, key=lambda item: (-item.date.toordinal(), item.record_id))
    state = {
        "month": year_month,
        "sourceFilename": source_filename,
        "sourceMarkdown": source_markdown,
        "entries": [
            {
                "recordId": entry.record_id,
                "statuses": [status.value for status in entry.interest_statuses],
            }
            for entry in sorted_entries
        ],
    }
    state_json = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    cards = "\n".join(_render_entry_card(entry) for entry in sorted_entries)
    summary_table = _render_summary_table(sorted_entries)
    stats = _render_stats(sorted_entries)
    generated = date.today().isoformat()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>长期关注台账 {html.escape(year_month)}</title>
  <style>
{_REGISTRY_CSS}
  </style>
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
        processEscapes: true
      }},
      options: {{
        skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
      }}
    }};
  </script>
  <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
</head>
<body>
  <script id="registry-state" type="application/json">{state_json}</script>
  <div class="registry-shell">
    <header class="registry-header">
      <div>
        <div class="kicker">DailyReport · 长期台账</div>
        <h1>{html.escape(year_month)} 深度关注记录</h1>
        <div class="registry-meta">
          <span>Source: {html.escape(source_filename)}</span>
          <span>Generated: {generated}</span>
          <span>MathJax formulas</span>
        </div>
      </div>
      {stats}
    </header>
    <div class="registry-layout">
      <aside class="registry-side">
        <section class="side-panel">
          <h2>状态同步</h2>
          <p>勾选条目状态后，点击“写回 Markdown”。页面会固定使用同名台账 Markdown，不再让你手动选择路径。</p>
          <div class="bound-source">已绑定：<strong>{html.escape(source_filename)}</strong></div>
          <button id="writeMarkdown" class="primary-button" type="button">写回 Markdown</button>
          <div id="syncMessage" class="sync-message" role="status">尚未修改状态。</div>
        </section>
        <section class="side-panel">
          <h2>视图</h2>
          <div class="view-switch">
            <button class="view-button is-active" type="button" data-view="entries">条目详情</button>
            <button class="view-button" type="button" data-view="summary">汇总表</button>
          </div>
        </section>
        <section class="side-panel">
          <h2>筛选</h2>
          <input id="searchInput" class="search-input" type="search" placeholder="搜索标题 / 关键词 / 摘要">
          <div class="filter-row" aria-label="属性筛选">
            <button class="filter-chip is-active" type="button" data-filter-attribute="all">全部</button>
            <button class="filter-chip" type="button" data-filter-attribute="论文">论文</button>
            <button class="filter-chip" type="button" data-filter-attribute="产品">产品</button>
            <button class="filter-chip" type="button" data-filter-attribute="项目">项目</button>
          </div>
        </section>
      </aside>
      <main class="registry-main" id="entriesView">
        <div class="view-toolbar">
          <h2>条目详情</h2>
          <button class="secondary-button inline-button" type="button" data-view="summary">查看汇总表</button>
        </div>
        <div class="entry-list">
          {cards}
        </div>
      </main>
      <main class="registry-main summary-main" id="summaryView" hidden>
        <div class="view-toolbar">
          <h2>汇总表</h2>
          <button class="secondary-button inline-button" type="button" data-view="entries">返回条目详情</button>
        </div>
        {summary_table}
      </main>
    </div>
  </div>
  <script>
{_REGISTRY_SCRIPT}
  </script>
</body>
</html>
"""


def _render_stats(entries: list[RegistryEntry]) -> str:
    total = len(entries)
    marked = sum(1 for entry in entries if entry.interest_statuses)
    star = sum(1 for entry in entries if entry.has_interest_status(InterestStatus.STAR))
    check = sum(1 for entry in entries if entry.has_interest_status(InterestStatus.CHECK))
    stats = [
        ("总条目", str(total)),
        ("已标记", str(marked)),
        ("重点", str(star)),
        ("可能有用", str(check)),
    ]
    items = "\n".join(
        f'<div class="stat"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in stats
    )
    return f'<div class="registry-stats">{items}</div>'


def _render_entry_card(entry: RegistryEntry) -> str:
    statuses = set(entry.interest_statuses)
    status_controls = "\n".join(
        _render_status_checkbox(entry.record_id, status, key, label, status in statuses)
        for status, key, label in _STATUS_DEFS
    )
    keywords = "\n".join(
        f'<span class="keyword">{html.escape(keyword)}</span>' for keyword in entry.keywords
    )
    summary_html = render_markdown_body(entry.summary_markdown).body_html
    search_text = " ".join([entry.title, " ".join(entry.keywords), entry.summary_markdown])
    return f"""<article id="{html.escape(entry.record_id.lower(), quote=True)}" class="registry-entry" data-record-id="{html.escape(entry.record_id, quote=True)}" data-attribute="{html.escape(entry.attribute.value, quote=True)}" data-search="{html.escape(search_text.lower(), quote=True)}">
  <header class="entry-header">
    <div class="entry-id-block">
      <a class="entry-id" href="#{html.escape(entry.summary_ref.lower(), quote=True)}">{html.escape(entry.record_id)}</a>
      <span class="entry-date">{entry.date.isoformat()}</span>
      <span class="entry-attribute">{html.escape(entry.attribute.value)}</span>
    </div>
    <h2>{html.escape(entry.title)}</h2>
    <div class="status-controls" data-record-id="{html.escape(entry.record_id, quote=True)}">
      {status_controls}
    </div>
  </header>
  <div class="keyword-row">{keywords}</div>
  <section class="entry-summary" id="{html.escape(entry.summary_ref.lower(), quote=True)}">
    {summary_html}
  </section>
</article>"""


def _render_summary_table(entries: list[RegistryEntry]) -> str:
    rows = "\n".join(_render_summary_row(entry) for entry in entries)
    return f"""<div class="summary-table-wrap">
  <table class="summary-table summary-table-compact">
    <colgroup>
      <col class="summary-date-col">
      <col class="summary-id-col">
      <col class="summary-title-col">
      <col class="summary-keywords-col">
      <col class="summary-attribute-col">
      <col class="summary-status-col">
    </colgroup>
    <thead>
      <tr>
        <th>日期</th>
        <th>记录ID</th>
        <th>标题</th>
        <th>关键词</th>
        <th>属性</th>
        <th>关注状态</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</div>"""


def _render_summary_row(entry: RegistryEntry) -> str:
    keywords = " / ".join(entry.keywords)
    status_badges = _render_status_badges(entry.interest_statuses)
    search_text = " ".join([entry.title, keywords, entry.summary_markdown])
    return f"""<tr class="summary-row" data-record-id="{html.escape(entry.record_id, quote=True)}" data-attribute="{html.escape(entry.attribute.value, quote=True)}" data-search="{html.escape(search_text.lower(), quote=True)}">
  <td class="summary-date"><time datetime="{entry.date.isoformat()}">{entry.date.strftime("%m-%d")}</time></td>
  <td><a class="table-record-id" href="#{html.escape(entry.record_id.lower(), quote=True)}" data-open-entry="{html.escape(entry.record_id, quote=True)}">{html.escape(entry.record_id)}</a></td>
  <td class="summary-title-cell">{html.escape(entry.title)}</td>
  <td class="summary-keywords-cell">{html.escape(keywords)}</td>
  <td class="summary-attribute-cell"><span class="entry-attribute">{html.escape(entry.attribute.value)}</span></td>
  <td class="summary-status-cell"><div class="status-badge-row" data-summary-statuses data-record-id="{html.escape(entry.record_id, quote=True)}">{status_badges}</div></td>
</tr>"""


def _render_status_badges(statuses: list[InterestStatus]) -> str:
    if not statuses:
        return '<span class="status-empty">未标记</span>'
    status_set = set(statuses)
    return "\n".join(
        f'<span class="status-badge status-badge-{key}"><span>{html.escape(status.value)}</span>{html.escape(label)}</span>'
        for status, key, label in _STATUS_DEFS
        if status in status_set
    )


def _render_status_checkbox(
    record_id: str,
    status: InterestStatus,
    key: str,
    label: str,
    checked: bool,
) -> str:
    checked_attr = " checked" if checked else ""
    return (
        '<label class="status-option">'
        f'<input type="checkbox" data-record-id="{html.escape(record_id, quote=True)}" '
        f'data-status="{html.escape(status.value, quote=True)}" data-status-key="{key}"{checked_attr}>'
        f'<span>{html.escape(status.value)}</span>{html.escape(label)}'
        "</label>"
    )


_REGISTRY_SCRIPT = r"""
    const registryState = JSON.parse(document.getElementById('registry-state').textContent);
    const statusOrder = ['*', '?', '✓'];
    const statusLabels = {
      '*': '非常关注',
      '?': '需要学习',
      '✓': '可能有用',
    };
    const statusClasses = {
      '*': 'status-badge-star',
      '?': 'status-badge-question',
      '✓': 'status-badge-check',
    };
    const syncMessage = document.getElementById('syncMessage');
    const statusByRecord = new Map(
      registryState.entries.map((entry) => [entry.recordId, new Set(entry.statuses || [])])
    );
    let dirty = false;

    function collectStatuses() {
      return new Map(
        Array.from(statusByRecord.entries()).map(([recordId, statuses]) => [
          recordId,
          statusOrder.filter((value) => statuses.has(value)).join(' '),
        ])
      );
    }

    function applyStatusesToMarkdown(markdownText) {
      const updates = collectStatuses();
      return markdownText.split(/\r?\n/).map((line) => {
        if (!line.trim().startsWith('|')) {
          return line;
        }
        for (const [recordId, display] of updates.entries()) {
          if (!line.includes(`| ${recordId} |`)) {
            continue;
          }
          const cells = line.split('|');
          if (cells.length < 8) {
            return line;
          }
          cells[cells.length - 2] = ` ${display} `;
          return cells.join('|');
        }
        return line;
      }).join('\n');
    }

    function setMessage(text, tone = '') {
      syncMessage.textContent = text;
      syncMessage.dataset.tone = tone;
    }

    function syncStatusControls(recordId) {
      const statuses = statusByRecord.get(recordId) || new Set();
      document.querySelectorAll(`input[data-record-id="${CSS.escape(recordId)}"][data-status]`).forEach((input) => {
        input.checked = statuses.has(input.dataset.status);
      });
      document.querySelectorAll(`[data-summary-statuses][data-record-id="${CSS.escape(recordId)}"]`).forEach((container) => {
        container.replaceChildren();
        const ordered = statusOrder.filter((status) => statuses.has(status));
        if (!ordered.length) {
          const empty = document.createElement('span');
          empty.className = 'status-empty';
          empty.textContent = '未标记';
          container.appendChild(empty);
          return;
        }
        ordered.forEach((status) => {
          const badge = document.createElement('span');
          badge.className = `status-badge ${statusClasses[status]}`;
          const marker = document.createElement('span');
          marker.textContent = status;
          badge.append(marker, statusLabels[status]);
          container.appendChild(badge);
        });
      });
    }

    function markDirty() {
      dirty = true;
      setMessage('状态已修改，尚未写回 Markdown。', 'dirty');
    }

    document.querySelectorAll('input[data-status]').forEach((input) => {
      input.addEventListener('change', () => {
        const recordId = input.dataset.recordId;
        const status = input.dataset.status;
        const statuses = statusByRecord.get(recordId) || new Set();
        if (input.checked) {
          statuses.add(status);
        } else {
          statuses.delete(status);
        }
        statusByRecord.set(recordId, statuses);
        syncStatusControls(recordId);
        markDirty();
      });
    });

    async function readBoundMarkdown() {
      if (registryState.sourceMarkdown) {
        return registryState.sourceMarkdown;
      }
      try {
        const response = await fetch(registryState.sourceFilename, { cache: 'no-store' });
        if (!response.ok) {
          throw new Error(`无法读取 ${registryState.sourceFilename}`);
        }
        return response.text();
      } catch (error) {
        throw new Error(`无法读取绑定文件 ${registryState.sourceFilename}`);
      }
    }

    function downloadBoundMarkdown(markdownText) {
      const blob = new Blob([markdownText], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = registryState.sourceFilename;
      link.click();
      URL.revokeObjectURL(url);
    }

    document.getElementById('writeMarkdown').addEventListener('click', async () => {
      try {
        const markdown = await readBoundMarkdown();
        const updated = applyStatusesToMarkdown(markdown);
        downloadBoundMarkdown(updated);
        dirty = false;
        setMessage(`已按 ${registryState.sourceFilename} 生成更新版 Markdown。静态 HTML 不能绕过浏览器安全策略直接覆盖本地文件。`, 'ok');
      } catch (error) {
        setMessage(`无法读取绑定文件：${error.message || error}`, 'error');
      }
    });

    const searchInput = document.getElementById('searchInput');
    const filterButtons = Array.from(document.querySelectorAll('[data-filter-attribute]'));
    const viewButtons = Array.from(document.querySelectorAll('[data-view]'));
    const entriesView = document.getElementById('entriesView');
    const summaryView = document.getElementById('summaryView');
    let activeAttribute = 'all';
    let activeView = 'entries';

    function setView(view) {
      activeView = view;
      entriesView.hidden = view !== 'entries';
      summaryView.hidden = view !== 'summary';
      const targetView = view === 'summary' ? summaryView : entriesView;
      viewButtons.forEach((button) => {
        button.classList.toggle('is-active', button.dataset.view === view);
      });
      if (view === 'summary') {
        history.replaceState(null, '', '#summary-table');
      } else if (location.hash === '#summary-table') {
        history.replaceState(null, '', '#entries');
      }
      targetView.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }

    function applyFilters() {
      const query = searchInput.value.trim().toLowerCase();
      document.querySelectorAll('.registry-entry, .summary-row').forEach((entry) => {
        const attributeMatch = activeAttribute === 'all' || entry.dataset.attribute === activeAttribute;
        const searchMatch = !query || entry.dataset.search.includes(query);
        entry.hidden = !(attributeMatch && searchMatch);
      });
    }

    viewButtons.forEach((button) => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        setView(button.dataset.view);
      });
    });

    document.querySelectorAll('[data-open-entry]').forEach((link) => {
      link.addEventListener('click', () => {
        setView('entries');
      });
    });

    searchInput.addEventListener('input', applyFilters);
    filterButtons.forEach((button) => {
      button.addEventListener('click', () => {
        filterButtons.forEach((item) => item.classList.remove('is-active'));
        button.classList.add('is-active');
        activeAttribute = button.dataset.filterAttribute;
        applyFilters();
      });
    });

    if (location.hash === '#summary-table') {
      setView('summary');
    }
"""


_REGISTRY_CSS = r"""
    :root {
      color-scheme: light;
      --page: #eef1f4;
      --paper: #fffdf8;
      --surface: #ffffff;
      --ink: #171b24;
      --body: #27303d;
      --muted: #687282;
      --line: #d9dee6;
      --line-strong: #b8c0cc;
      --blue: #174d7a;
      --teal: #1d6f73;
      --amber: #8a5a00;
      --amber-soft: #fff4d9;
      --green: #2f6b4f;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--page);
      color: var(--ink);
      font-family: "Aptos", "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      letter-spacing: 0;
    }

    .registry-shell {
      width: min(1440px, 100%);
      margin: 0 auto;
      padding: 28px 28px 80px;
    }

    .registry-header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(360px, 520px);
      gap: 24px;
      align-items: end;
      padding: 30px 0 24px;
      border-bottom: 2px solid #202635;
      margin-bottom: 24px;
    }

    .kicker {
      color: var(--teal);
      font-size: 13px;
      font-weight: 760;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 12px;
    }

    h1 {
      margin: 0;
      font-size: 40px;
      line-height: 1.12;
      font-weight: 780;
    }

    .registry-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
      color: var(--muted);
      font-size: 12.5px;
    }

    .registry-meta span {
      min-height: 28px;
      padding: 5px 9px;
      border: 1px solid var(--line);
      border-radius: 5px;
      background: rgba(255, 253, 248, 0.78);
    }

    .registry-stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      overflow: hidden;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: var(--line-strong);
    }

    .stat {
      padding: 14px 16px;
      background: var(--paper);
    }

    .stat span {
      display: block;
      margin-bottom: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 740;
    }

    .stat strong {
      font-size: 24px;
      line-height: 1;
    }

    .registry-layout {
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
      gap: 28px;
      align-items: start;
    }

    .registry-side {
      position: sticky;
      top: 20px;
      display: grid;
      gap: 16px;
    }

    .side-panel {
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
    }

    .side-panel h2 {
      margin: 0 0 10px;
      font-size: 16px;
    }

    .side-panel p {
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.65;
    }

    button,
    input {
      font: inherit;
    }

    .primary-button,
    .secondary-button {
      width: 100%;
      min-height: 36px;
      margin-top: 8px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 740;
    }

    .primary-button {
      border: 1px solid #202635;
      background: #202635;
      color: #ffffff;
    }

    .secondary-button {
      border: 1px solid var(--line-strong);
      background: #ffffff;
      color: var(--blue);
    }

    .sync-message {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.5;
    }

    .sync-message[data-tone="ok"] {
      color: var(--green);
    }

    .sync-message[data-tone="dirty"],
    .sync-message[data-tone="warn"] {
      color: var(--amber);
    }

    .sync-message[data-tone="error"] {
      color: #a33434;
    }

    .bound-source {
      margin: 0 0 8px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.45;
    }

    .bound-source strong {
      color: var(--ink);
      font-weight: 760;
    }

    .view-switch {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }

    .view-button {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--muted);
      cursor: pointer;
      font-size: 13px;
      font-weight: 740;
    }

    .view-button.is-active {
      border-color: var(--blue);
      background: #edf4f9;
      color: var(--blue);
    }

    .search-input {
      width: 100%;
      min-height: 36px;
      padding: 8px 10px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: #ffffff;
    }

    .filter-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 12px;
    }

    .filter-chip {
      min-height: 30px;
      padding: 5px 9px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #ffffff;
      color: var(--muted);
      cursor: pointer;
      font-size: 12.5px;
      font-weight: 700;
    }

    .filter-chip.is-active {
      border-color: var(--blue);
      color: var(--blue);
    }

    .registry-main {
      display: grid;
      gap: 16px;
    }

    .registry-main[hidden] {
      display: none !important;
    }

    .view-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 15px 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--paper);
    }

    .view-toolbar h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.25;
    }

    .inline-button {
      width: auto;
      min-width: 128px;
      margin-top: 0;
      padding: 0 12px;
    }

    .entry-list {
      display: grid;
      gap: 16px;
    }

    .registry-entry {
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: 0 10px 24px rgba(27, 34, 45, 0.045);
    }

    .entry-header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px 18px;
      padding: 18px 20px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }

    .entry-id-block {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      align-items: center;
      grid-column: 1 / -1;
    }

    .entry-id,
    .entry-date,
    .entry-attribute {
      min-height: 24px;
      padding: 4px 7px;
      border-radius: 5px;
      font-size: 12px;
      font-weight: 760;
      line-height: 1.2;
      text-decoration: none;
    }

    .entry-id {
      background: #202635;
      color: #ffffff;
    }

    .entry-date,
    .entry-attribute {
      border: 1px solid var(--line);
      background: #ffffff;
      color: var(--muted);
    }

    .entry-header h2 {
      margin: 0;
      color: var(--ink);
      font-size: 19px;
      line-height: 1.35;
      font-weight: 760;
      text-wrap: pretty;
    }

    .status-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }

    .status-option {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      min-height: 30px;
      padding: 5px 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #ffffff;
      color: #344154;
      cursor: pointer;
      font-size: 12.5px;
      font-weight: 700;
      white-space: nowrap;
    }

    .status-option input {
      accent-color: var(--blue);
    }

    .status-option span {
      font-weight: 900;
    }

    .keyword-row {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      padding: 14px 20px 0;
    }

    .keyword {
      padding: 4px 8px;
      border-radius: 999px;
      background: #edf2f6;
      color: #485568;
      font-size: 12.5px;
      font-weight: 700;
    }

    .entry-summary {
      padding: 14px 20px 22px;
      color: var(--body);
      font-family: "Iowan Old Style", "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", Georgia, serif;
      font-size: 16.5px;
      line-height: 1.86;
    }

    .entry-summary p {
      margin: 0 0 13px;
    }

    .entry-summary a {
      color: var(--blue);
      text-decoration: underline;
      text-decoration-color: rgba(23, 77, 122, 0.32);
      text-underline-offset: 3px;
    }

    .entry-summary code {
      padding: 0.12rem 0.32rem;
      border: 1px solid #d8e1ea;
      border-radius: 5px;
      background: #eef2f7;
      color: #1e293b;
      font-size: 0.9em;
    }

    .math-block {
      margin: 16px 0;
      padding: 14px;
      overflow-x: auto;
      border: 1px solid #cfd7e2;
      border-radius: 8px;
      background: #ffffff;
      text-align: center;
    }

    .summary-table-wrap {
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 10px 24px rgba(27, 34, 45, 0.045);
    }

    .summary-table {
      width: 100%;
      min-width: 0;
      table-layout: fixed;
      border-collapse: collapse;
      font-size: 12.5px;
      line-height: 1.42;
    }

    .summary-date-col {
      width: 58px;
    }

    .summary-id-col {
      width: 104px;
    }

    .summary-title-col {
      width: 31%;
    }

    .summary-keywords-col {
      width: 38%;
    }

    .summary-attribute-col {
      width: 54px;
    }

    .summary-status-col {
      width: 122px;
    }

    .summary-table th,
    .summary-table td {
      padding: 10px 9px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
      overflow-wrap: anywhere;
    }

    .summary-table th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #eef1f5;
      color: #334155;
      font-weight: 760;
      white-space: nowrap;
    }

    .summary-date {
      color: var(--muted);
      font-weight: 720;
      white-space: nowrap;
    }

    .summary-title-cell {
      color: #111827;
      font-weight: 650;
    }

    .summary-keywords-cell {
      color: #243244;
    }

    .summary-attribute-cell .entry-attribute {
      display: inline-flex;
      min-width: 0;
      white-space: nowrap;
    }

    .summary-table tr:last-child td {
      border-bottom: 0;
    }

    .summary-table tr:nth-child(even) td {
      background: #fafbfd;
    }

    .table-record-id {
      color: var(--blue);
      font-weight: 760;
      text-decoration: none;
      white-space: nowrap;
    }

    .status-badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }

    .status-badge,
    .status-empty {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border: 1px solid #d2dbe6;
      border-radius: 999px;
      background: #f8fafc;
      color: #334155;
      font-size: 11.5px;
      font-weight: 740;
      line-height: 1.2;
      white-space: nowrap;
    }

    .status-badge span {
      margin-right: 4px;
      color: var(--blue);
      font-weight: 840;
    }

    .status-badge-star {
      border-color: #e7d39a;
      background: #fff8db;
      color: #6b4c00;
    }

    .status-badge-question {
      border-color: #cfd8e5;
      background: #f3f6fb;
      color: #334155;
    }

    .status-badge-check {
      border-color: #b8d4c0;
      background: #edf8ef;
      color: #1f6b3b;
    }

    .status-empty {
      color: var(--muted);
      font-weight: 650;
    }

    @media (max-width: 1080px) {
      .registry-header,
      .registry-layout {
        grid-template-columns: 1fr;
      }

      .registry-side {
        position: static;
      }
    }

    @media (max-width: 760px) {
      .registry-shell {
        padding: 20px 12px 48px;
      }

      h1 {
        font-size: 30px;
      }

      .registry-stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .entry-header {
        grid-template-columns: 1fr;
      }

      .status-controls {
        justify-content: flex-start;
      }
    }
"""
