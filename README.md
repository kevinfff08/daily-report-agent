# DailyReport — 每日 AI/ML 情报聚合系统

PhD-level 每日情报聚合工具，监控 arXiv 论文、大厂官方博客、视频博主、开源项目、新产品发布、社区动态，生成两阶段深度报告。

## 功能特性

- **8 源数据采集**：
  - **学术论文**：arXiv API + Semantic Scholar API
  - **大厂博客**：Tavily Search 定向搜索（OpenAI、Anthropic、Google DeepMind、Meta、Microsoft、NVIDIA 等 10 家）
  - **视频博主**：YouTube Data API + Bilibili API
  - **开源项目**：GitHub Trending
  - **新产品**：Product Hunt GraphQL API
  - **社区热点**：Hacker News Firebase API
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
- API Keys（见下方配置部分）

### 安装依赖

```bash
conda activate research_tools
pip install -e .
```

开发环境（含测试依赖）：

```bash
pip install -e ".[dev]"
```

### 配置

1. **环境变量**：复制并编辑 `.env` 文件

```bash
cp .env.example .env
```

编辑 `.env`，填入 API Keys：

```
# 必需
ANTHROPIC_API_KEY=sk-ant-...    # Claude LLM 调用
YOUTUBE_API_KEY=AIza...          # YouTube 视频采集
TAVILY_API_KEY=tvly-...          # 大厂博客搜索
PRODUCT_HUNT_TOKEN=...           # Product Hunt 新产品

# 可选
SEMANTIC_SCHOLAR_API_KEY=        # 提高 Semantic Scholar 速率限制
GITHUB_TOKEN=ghp_...             # 提高 GitHub 速率限制
```

2. **数据源配置**：复制并编辑 `config/sources.yaml`

```bash
cp config/sources.example.yaml config/sources.yaml
```

按需调整各数据源参数：YouTube 频道、Bilibili UP主、arXiv 类别、搜索关键词等。

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
python -m src.cli collect --date 2026-03-10 --sources arxiv,hackernews,youtube

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
│   ├── collectors/               # 8 个数据采集器
│   │   ├── arxiv_collector.py           # arXiv Atom API
│   │   ├── hacker_news_collector.py     # HN Firebase API
│   │   ├── youtube_collector.py         # YouTube Data API v3
│   │   ├── bilibili_collector.py        # Bilibili API (WBI signed)
│   │   ├── semantic_scholar_collector.py # Semantic Scholar API
│   │   ├── github_trending_collector.py  # GitHub Trending HTML
│   │   ├── product_hunt_collector.py    # Product Hunt GraphQL
│   │   └── tavily_collector.py          # Tavily Search (大厂博客)
│   ├── analyzers/                # LLM 分析层（论文/业界/社区）
│   ├── reporters/                # 报告生成层（概览/深度）
│   ├── llm/                      # Claude API 封装 + Prompt 模板
│   └── storage/                  # JSON 文件持久化
├── config/
│   ├── sources.yaml              # 数据源配置
│   └── sources.example.yaml      # 配置示例
├── data/                         # 运行时数据（gitignored）
├── output/                       # 最终报告（gitignored）
├── logs/                         # 日志文件（gitignored）
└── tests/                        # 134 个测试
```

## 分析器路由

| 来源类型 | 分析器 | 输出类别 |
|---------|--------|---------|
| arXiv, Semantic Scholar | PaperAnalyzer | 论文 |
| Tavily Search, Product Hunt | IndustryAnalyzer | 业界动态 |
| Hacker News, YouTube, Bilibili, GitHub Trending | SocialAnalyzer | 社区热点 |

## 开发

### 运行测试

```bash
conda activate research_tools
python -m pytest tests/ -v
```

### 日志

- 日志文件：`logs/YYYY-MM-DD.log`（DEBUG 级别）
- 控制台输出：WARNING+ 级别

### LLM 代理模式

如果使用代理服务器访问 Claude API：

```
LLM_MODE=setup-token
LLM_PROXY_URL=http://localhost:8317
```
