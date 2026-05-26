# DailyReport — 每日 AI/ML 情报聚合系统

PhD-level 每日情报工具，监控 arXiv、顶会/Blog、社区讨论、开源项目和新产品发布，生成两阶段报告：
- Stage 1：`daily_report.md` / `daily_report.html`，适合 10-15 分钟快速浏览
- Stage 2：`deep_dive_report.md` / `deep_dive_report.html`，针对你手选条目的深度分析

DailyReport 支持双模式使用：完整 CLI 工作流用于命令行自动化和传统操作，同时提供本地桌面 App，把流程控制、HTML 报告阅读和台账状态维护合在同一个窗口中。

## 功能概览

- 8 个数据源：arXiv、Semantic Scholar、Tavily、Product Hunt、Hacker News、YouTube、Bilibili、GitHub Trending
- 两阶段报告流程：先总览，再按编号深挖
- OpenAI / Anthropic / DeepSeek 三适配，支持 API Key，且保留现有 CLIProxy 转接能力
- Markdown 数学公式规范化，便于后续 LaTeX / PDF 链路使用
- Markdown 与 HTML 双格式输出；HTML 报告内置阅读模板，并通过 MathJax 渲染行内和块级公式
- 相邻 3 天概览正文自动做跨天重复降权，减少连续几天反复出现相同条目
- 深度分析完成后自动登记到长期台账
- 长期台账支持命令行展示、状态维护和历史条目检索

## 环境准备

### 前置条件

- Python 3.14+
- Conda 环境：`research_tools`
- 必要 API Key：见下方配置说明

### 安装

```bash
conda activate research_tools
pip install -e .
```

桌面 App 需要 `pywebview`，已包含在项目依赖中。当前 Windows/Python 3.14 环境默认使用 Qt 后端，因此还需要 `PySide6` 和 `QtPy`。如果 `pip install -e .` 在安装 `pywebview` 的 Windows 默认后端依赖时失败，可以在 `research_tools` 环境中使用：

```bash
python -m pip install --no-deps pywebview bottle proxy_tools QtPy PySide6
```

开发环境：

```bash
pip install -e ".[dev]"
```

## 配置

### `.env`

复制示例：

```bash
cp .env.example .env
```

常用配置：

```env
# LLM
LLM_PROVIDER=anthropic          # anthropic | openai | deepseek
LLM_MODE=api-key                # api-key | setup-token
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-proj-...
# DEEPSEEK_API_KEY=sk-...
# LLM_PROXY_URL=http://localhost:8317
# LLM_MODEL=gpt-4.1-mini
# LLM_TIMEOUT_SECONDS=300

# Optional: deep-dive paper input length limit (characters)
# - Anthropic default: 40000
# - OpenAI default: 80000
# - DeepSeek default: 80000
# PAPER_MAX_CHARS=80000

# Optional: deep-dive output token limit
# - Anthropic default: 8192
# - OpenAI default: 12000
# - DeepSeek default: 12000
# DEEP_DIVE_MAX_TOKENS=12000

# Data source keys
YOUTUBE_API_KEY=AIza...
TAVILY_API_KEY=tvly-...
PRODUCT_HUNT_TOKEN=...
# Optional
SEMANTIC_SCHOLAR_API_KEY=
GITHUB_TOKEN=
```

当使用 CLIProxy 时：

```env
LLM_PROVIDER=openai             # 或 anthropic
LLM_MODE=setup-token
LLM_PROXY_URL=http://localhost:8317
```

OpenAI 适配会自动把 `LLM_PROXY_URL` 规范到 `/v1`，例如 `http://localhost:8317` 会自动变成 `http://localhost:8317/v1`。

### Deep Dive 长度参数

可选参数：

- `PAPER_MAX_CHARS`
  控制 deep-dive 中论文正文输入给 LLM 前的字符上限。PDF 抽取文本和论文页回退文本都会按这个上限截断。
- `DEEP_DIVE_MAX_TOKENS`
  控制 deep-dive 单条条目生成时传给 LLM 的输出 token 上限。
- `LLM_TIMEOUT_SECONDS`
  控制 OpenAI-compatible / CLIProxy HTTP 请求超时时间，默认 300 秒。

默认值：

- Anthropic：`PAPER_MAX_CHARS=40000`，`DEEP_DIVE_MAX_TOKENS=8192`
- OpenAI：`PAPER_MAX_CHARS=80000`，`DEEP_DIVE_MAX_TOKENS=12000`
- DeepSeek：`PAPER_MAX_CHARS=80000`，`DEEP_DIVE_MAX_TOKENS=12000`

如果你在 `.env` 里显式设置了 `PAPER_MAX_CHARS` 或 `DEEP_DIVE_MAX_TOKENS`，则会覆盖 provider 默认值，并且对 Anthropic / OpenAI / DeepSeek 通用生效。

### `config/sources.yaml`

复制示例：

```bash
cp config/sources.example.yaml config/sources.yaml
```

按需调整 YouTube 频道、Bilibili UP 主、arXiv 分类、Tavily 搜索项等数据源参数。

## 常用命令

```bash
# 查看帮助
python -m src.cli --help

# 系统状态
python -m src.cli status

# 只采集
python -m src.cli collect
python -m src.cli collect --date 2026-03-25 --sources arxiv,hackernews,tavily

# 生成 Stage 1 概览报告
python -m src.cli report
python -m src.cli report --date 2026-03-25

# 一键跑完整流程（collect + overview）
python -m src.cli run

# 生成 Stage 2 深度分析
python -m src.cli deep-dive --items "1,3,15"
python -m src.cli deep-dive --date 2026-03-25 --items "1,3,15"

# 从已有 Markdown 生成 HTML（不调用 LLM）
python -m src.cli html --date 2026-03-25
python -m src.cli html --start-date 2026-03-01 --end-date 2026-05-31
python -m src.cli html --all

# 启动本地桌面 App（控制流程 + 内嵌 HTML 报告阅读）
python -m src.cli app
python -m src.cli app --date 2026-03-25
```

## 桌面 App

Windows 下可以双击 `start_app.bat` 启动桌面 App。`start.bat` 保留为传统 CLI 启动脚本，不改变原有命令行工作流。

桌面 App 是本地 pywebview 窗口，不启动 HTTP 服务，也不对外暴露 API。左侧用于选择日期、运行 collect/report/run/html、选择 deep-dive 条目、刷新台账和写回关注状态；右侧直接内嵌显示 `daily_report.html`、`deep_dive_report.html` 和 `records/YYYY-MM-record.html`。在桌面 App 内打开台账 HTML 后，直接在 HTML 里勾选关注状态并点击“写回 Markdown”，会通过本地 Python bridge 更新同名 `records/YYYY-MM-record.md` 并刷新 HTML；普通浏览器打开该 HTML 时仍保留下载更新版 Markdown 的 fallback。

如果 `LLM_MODE=setup-token`，`start_app.bat` 会沿用 `start.bat` 的逻辑先启动 CLIProxyAPI，再启动桌面 App。

## 长期台账

### 文件组织

- 实际台账按月存储：`records/YYYY-MM-record.md`
- HTML 阅读版同步存储：`records/YYYY-MM-record.html`
- 示例文件：`records/2026-03-record.example.md`
- 实际台账被 `.gitignore` 忽略，示例文件保留在仓库中用于公开展示格式

### 台账结构

主表列：
- `日期`
- `记录ID`
- `标题`
- `关键词`
- `属性`
- `摘要`
- `我的关注状态`

说明：
- `记录ID` 固定为 `YYYYMMDD-XXX`
- `摘要` 列只保存稳定引用号，例如 `SUM-20260325-001`
- 完整摘要放在同一月文件下半部分的“摘要附录”中
- HTML 版提供汇总表、条目详情、搜索、属性筛选和关注状态勾选；勾选后可点击“写回 Markdown”按同名 Markdown 文件生成更新版
- 自动同步只覆盖自动字段：标题、关键词、属性、摘要
- 你的手动字段 `我的关注状态` 会被保留

关注状态含义：
- `*`：非常关注
- `?`：需要进一步学习
- `✓`：可能有用
- 同一条记录可同时拥有多个状态，例如 `* ?`

### 台账命令

```bash
# 查看全部历史记录
python -m src.cli registry show

# 查看指定月份
python -m src.cli registry show --month 2026-03

# 按状态过滤
python -m src.cli registry show --status star

# 更新关注状态
python -m src.cli registry mark --id 20260325-001 --status star
python -m src.cli registry mark --id 20260325-001 --status question
python -m src.cli registry mark --id 20260325-001 --status star,question --mode set
python -m src.cli registry mark --id 20260325-001 --status check
python -m src.cli registry mark --id 20260325-001 --status none
python -m src.cli registry mark --id 20260325-001 --status star --mode remove

# 生成/修复台账 HTML
python -m src.cli registry html --month 2026-03
python -m src.cli registry html --all
python -m src.cli registry repair

# 检索最接近的历史条目
python -m src.cli registry find --query "multi-agent safety"
python -m src.cli registry find --query "agent workflow IDE" --limit 5
```

### `registry find` 的检索顺序

1. 先在 `关键词` 字段里做纯代码匹配
2. 若 0 命中，再在 `摘要` 正文里做纯代码匹配
3. 若仍 0 命中，再把查询和全部月度记录交给 LLM 做最终相关性判断

CLI 输出固定显示：`文件名`、`日期`、`记录ID`、`标题`。

## 数据产物

```text
data/
  raw/YYYY-MM/YYYY-MM-DD/                # 原始采集结果
  analyzed/YYYY-MM/YYYY-MM-DD/           # 分析结果
  reports/YYYY-MM/YYYY-MM-DD/
    overview.md                  # Stage 1 markdown
    overview.html                # Stage 1 HTML
    overview_model.json          # Stage 1 结构化结果
    items_index.json             # 候选条目索引
    overview_snippets.json       # 已入选条目的简版摘要
    recent_duplicate_matches.json # 跨天重复命中调试信息
    deep_dive.md                 # Stage 2 markdown 数据
    deep_dive.html               # Stage 2 HTML

output/
  YYYY-MM/YYYY-MM-DD/
    daily_report.md              # 最终概览报告
    daily_report.html            # 最终概览 HTML 报告
    deep_dive_report.md          # 最终深度分析报告
    deep_dive_report.html        # 最终深度分析 HTML 报告

logs/
  YYYY-MM/YYYY-MM-DD.log

records/
  YYYY-MM-record.md              # 月度长期台账（gitignored）
  2026-03-record.example.md      # 公开示例
```

## 典型工作流

```bash
# 1. 跑当日概览
python -m src.cli run

# 2. 阅读 output/YYYY-MM/YYYY-MM-DD/daily_report.html，挑选编号

# 3. 生成深度分析
python -m src.cli deep-dive --items "1,5,12"

# 4. 深度分析完成后，条目会自动登记到当月 records/YYYY-MM-record.md

# 5. 后续阅读完可更新关注状态（可叠加多个状态）
python -m src.cli registry mark --id 20260325-001 --status star
```

## 开发与测试

```bash
conda activate research_tools
python -m pytest tests/ -v
```

日志：
- 文件日志：`logs/YYYY-MM/YYYY-MM-DD.log`
- 控制台：`WARNING+`

## 项目结构

```text
src/
  cli.py
  desktop/
  orchestrator.py
  llm/
  collectors/
  analyzers/
  reporters/
  registry/
  models/
  storage/
  utils/
```

其中：
- `desktop/` 提供 pywebview 本地桌面壳，用于流程控制、后台任务状态和内嵌 HTML 报告阅读
- `reporters/overview_reporter.py` 负责生成 `daily_report.md` 和 `overview_snippets.json`
- `reporters/html_renderer.py` 负责把报告 Markdown 渲染为独立 HTML，并为历史报告补生成 HTML
- `filters/recent_duplicates.py` 负责恢复近 3 天正文条目并计算跨天重复 penalty
- `reporters/deep_dive_reporter.py` 负责生成 `deep_dive_report.md`
- `registry/manager.py` 负责深度分析登记和历史条目检索
- `storage/registry_store.py` 负责月度 Markdown 台账的确定性读写

## 跨天重复降权

- 只对比前 3 天真正进入 `daily_report` 正文的条目，不看全部候选索引
- 处理方式是降权，不是硬删除；当天确实重要的内容仍可能保留
- 判重顺序固定为：稳定 ID / URL 优先，标题高相似补充
- 调试结果会写到 `data/reports/YYYY-MM/YYYY-MM-DD/recent_duplicate_matches.json`
