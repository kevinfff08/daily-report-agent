# DailyReport — 每日 AI/ML 情报聚合系统

PhD-level 每日情报工具，监控 arXiv、顶会/Blog、社区讨论、开源项目和新产品发布，生成两阶段报告：
- Stage 1：`daily_report.md`，适合 10-15 分钟快速浏览
- Stage 2：`deep_dive_report.md`，针对你手选条目的深度分析

## 功能概览

- 8 个数据源：arXiv、Semantic Scholar、Tavily、Product Hunt、Hacker News、YouTube、Bilibili、GitHub Trending
- 两阶段报告流程：先总览，再按编号深挖
- OpenAI / Anthropic / DeepSeek 三适配，支持 API Key，且保留现有 CLIProxy 转接能力
- Markdown 数学公式规范化，便于后续 LaTeX / PDF 链路使用
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

# Optional: deep-dive paper input length limit (characters)
# - Anthropic default: 40000
# - OpenAI default: 120000
# - DeepSeek default: 120000
# PAPER_MAX_CHARS=120000

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

默认值：

- Anthropic：`PAPER_MAX_CHARS=40000`，`DEEP_DIVE_MAX_TOKENS=8192`
- OpenAI：`PAPER_MAX_CHARS=120000`，`DEEP_DIVE_MAX_TOKENS=12000`
- DeepSeek：`PAPER_MAX_CHARS=120000`，`DEEP_DIVE_MAX_TOKENS=12000`

如果你在 `.env` 里显式设置了这两个参数，则会覆盖 provider 默认值，并且对 Anthropic / OpenAI / DeepSeek 通用生效。

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
```

## 长期台账

### 文件组织

- 实际台账按月存储：`records/YYYY-MM-record.md`
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
    overview_model.json          # Stage 1 结构化结果
    items_index.json             # 候选条目索引
    overview_snippets.json       # 已入选条目的简版摘要
    recent_duplicate_matches.json # 跨天重复命中调试信息
    deep_dive.md                 # Stage 2 markdown 数据

output/
  YYYY-MM/YYYY-MM-DD/
    daily_report.md              # 最终概览报告
    deep_dive_report.md          # 最终深度分析报告

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

# 2. 阅读 output/YYYY-MM/YYYY-MM-DD/daily_report.md，挑选编号

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
- `reporters/overview_reporter.py` 负责生成 `daily_report.md` 和 `overview_snippets.json`
- `filters/recent_duplicates.py` 负责恢复近 3 天正文条目并计算跨天重复 penalty
- `reporters/deep_dive_reporter.py` 负责生成 `deep_dive_report.md`
- `registry/manager.py` 负责深度分析登记和历史条目检索
- `storage/registry_store.py` 负责月度 Markdown 台账的确定性读写

## 跨天重复降权

- 只对比前 3 天真正进入 `daily_report` 正文的条目，不看全部候选索引
- 处理方式是降权，不是硬删除；当天确实重要的内容仍可能保留
- 判重顺序固定为：稳定 ID / URL 优先，标题高相似补充
- 调试结果会写到 `data/reports/YYYY-MM/YYYY-MM-DD/recent_duplicate_matches.json`
