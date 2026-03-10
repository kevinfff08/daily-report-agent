# DailyReport — 每日 AI/ML 情报聚合系统

PhD-level 每日情报聚合工具，监控 arXiv 论文、公司博客、科技新闻、Reddit/HN 社区动态，生成两阶段深度报告。

## 功能特性

- **多源数据采集**：arXiv 论文、RSS 订阅（公司博客/新闻/学术博客）、Reddit、Hacker News
- **Claude LLM 驱动分析**：批量结构化分析（论文/业界/社区三类分析器）
- **两阶段报告系统**：
  - **Stage 1 概览报告**（~15 分钟阅读）：全量覆盖，带编号索引，PhD-level 信息密度
  - **Stage 2 深度分析**（30-60 分钟阅读）：用户选择感兴趣的编号，生成深入分析
- **全量索引**：不做智能过滤，所有条目编号列出，用户自主选择深入方向
- **手动触发**：无定时调度，按需执行

## 环境准备

### 前置条件

- Python 3.12+
- Conda（推荐使用 `research_tools` 环境）
- Anthropic API Key

### 安装依赖

```bash
conda activate research_tools
pip install feedparser PyYAML
```

或通过 pyproject.toml 安装：

```bash
pip install -e .
```

### 配置

1. **环境变量**：复制并编辑 `.env` 文件

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```
LLM_MODE=api-key
ANTHROPIC_API_KEY=sk-ant-...
```

2. **数据源配置**：复制并编辑 `config/sources.yaml`

```bash
cp config/sources.example.yaml config/sources.yaml
```

按需调整 arXiv 类别、RSS 源列表、Reddit 子版块、HN 过滤条件。

## 使用方法

### 快速启动（Windows）

双击 `start.bat`，会自动激活 conda 环境并显示帮助信息。

### CLI 命令

```bash
# 查看帮助
python -m src.cli --help

# 查看系统状态和配置
python -m src.cli status

# 采集今日数据（所有数据源）
python -m src.cli collect

# 采集指定日期、指定数据源
python -m src.cli collect --date 2026-03-10 --sources arxiv,hackernews

# 生成 Stage 1 概览报告（自动补全缺失的采集/分析步骤）
python -m src.cli report

# 全流程一键执行（采集 + 分析 + 概览报告）
python -m src.cli run

# 根据概览报告中的编号，生成 Stage 2 深度分析
python -m src.cli deep-dive --items "1,3,15,23"
```

### 典型工作流

```bash
# 1. 采集 + 生成概览报告
python -m src.cli run

# 2. 阅读 output/YYYY-MM-DD/daily_report.md，选出感兴趣的编号

# 3. 生成深度分析
python -m src.cli deep-dive --items "1,5,12"

# 4. 阅读 output/YYYY-MM-DD/deep_dive_report.md
```

## 项目结构

```
DailyReport/
├── src/
│   ├── cli.py                    # Typer CLI 入口（5 个命令）
│   ├── orchestrator.py           # 核心调度器
│   ├── logging_config.py         # 集中式日志
│   ├── models/                   # Pydantic v2 数据模型
│   │   ├── source.py             # SourceItem, SourceType
│   │   ├── analysis.py           # AnalyzedItem, PaperAnalysis 等
│   │   ├── report.py             # DailyOverview, DeepDiveReport
│   │   └── config.py             # SourceConfig
│   ├── collectors/               # 数据采集层
│   │   ├── arxiv_collector.py    # arXiv API
│   │   ├── rss_collector.py      # RSS/Atom（博客、新闻）
│   │   ├── reddit_collector.py   # Reddit JSON API
│   │   └── hacker_news_collector.py  # HN Firebase API
│   ├── analyzers/                # LLM 分析层
│   │   ├── paper_analyzer.py     # 论文结构化分析
│   │   ├── industry_analyzer.py  # 业界动态分析
│   │   └── social_analyzer.py    # 社区讨论分析
│   ├── reporters/                # 报告生成层
│   │   ├── overview_reporter.py  # Stage 1 概览报告
│   │   └── deep_dive_reporter.py # Stage 2 深度报告
│   ├── llm/                      # LLM 交互层
│   │   ├── client.py             # Claude API 封装
│   │   └── prompts/v1/           # Prompt 模板
│   └── storage/
│       └── local_store.py        # JSON 文件持久化
├── config/
│   ├── sources.yaml              # 数据源配置（gitignored）
│   └── sources.example.yaml      # 配置示例
├── data/                         # 运行时数据（gitignored）
│   ├── raw/YYYY-MM-DD/           # 原始采集数据
│   ├── analyzed/YYYY-MM-DD/      # 分析结果
│   └── reports/YYYY-MM-DD/       # 报告数据模型
├── output/YYYY-MM-DD/            # 最终报告（gitignored）
├── logs/                         # 日志文件（gitignored）
└── tests/                        # 测试套件
```

## 数据流

```
采集 (collect)           分析 (analyze)           报告 (report)
┌─────────┐             ┌──────────┐             ┌──────────────┐
│ arXiv   │──┐          │ Paper    │──┐          │ Overview     │
│ RSS     │──┤ raw/     │ Industry │──┤ analyzed/│ Reporter     │→ Stage 1
│ Reddit  │──┤ YYYY-MM-DD│ Social  │──┘ YYYY-MM-DD│              │  报告
│ HN      │──┘          └──────────┘             └──────────────┘
                                                  ┌──────────────┐
                                                  │ Deep Dive    │
                                                  │ Reporter     │→ Stage 2
                                                  └──────────────┘  报告
```

## 配置说明

### arXiv 类别

默认监控：`cs.AI`, `cs.CL`, `cs.CV`, `cs.LG`, `cs.SE`

在 `config/sources.yaml` 中调整 `arxiv.categories`。

### RSS 源

支持三类 RSS 源：
- `industry`：公司博客（OpenAI、Anthropic、Google AI 等）
- `news`：科技新闻（TechCrunch AI、The Verge AI 等）
- `academic`：学术博客（BAIR、Distill.pub 等）

### Reddit

默认子版块：`r/MachineLearning`, `r/LocalLLaMA`

### Hacker News

- `min_score`：最低分数过滤（默认 50）
- `keywords`：关键词过滤（AI、LLM、machine learning 等）

## 开发

### 运行测试

```bash
conda activate research_tools
python -m pytest tests/ -v
```

### 日志

- 日志文件：`logs/YYYY-MM-DD.log`（DEBUG 级别）
- 控制台输出：WARNING+ 级别
- 格式：`时间 | 级别 | 模块 | 消息`

### LLM 代理模式

如果使用代理服务器访问 Claude API：

```
LLM_MODE=setup-token
LLM_PROXY_URL=http://localhost:8317
```

## 技术栈

- **运行时**：Python 3.12+, asyncio
- **CLI**：Typer + Rich
- **数据模型**：Pydantic v2
- **HTTP 客户端**：httpx (async)
- **LLM**：Anthropic Claude API
- **RSS 解析**：feedparser
- **配置**：PyYAML
- **测试**：pytest + pytest-asyncio
