"""Data models for source configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ArxivConfig(BaseModel):
    """Configuration for arXiv collector."""

    categories: list[str] = Field(default_factory=lambda: ["cs.AI", "cs.CL", "cs.CV", "cs.LG"])
    max_results_per_category: int = Field(default=50)


class HackerNewsConfig(BaseModel):
    """Configuration for Hacker News collector."""

    min_score: int = Field(default=50)
    max_items: int = Field(default=30)
    keywords: list[str] = Field(
        default_factory=lambda: ["AI", "LLM", "machine learning", "neural", "GPT", "Claude", "transformer"]
    )


class YouTubeChannelConfig(BaseModel):
    """Configuration for a single YouTube channel."""

    name: str
    channel_id: str


class YouTubeConfig(BaseModel):
    """Configuration for YouTube collector."""

    channels: list[YouTubeChannelConfig] = Field(default_factory=list)
    max_results_per_channel: int = Field(default=5)


class BilibiliUserConfig(BaseModel):
    """Configuration for a single Bilibili UP主."""

    name: str
    uid: int


class BilibiliConfig(BaseModel):
    """Configuration for Bilibili collector."""

    users: list[BilibiliUserConfig] = Field(default_factory=list)
    max_results_per_user: int = Field(default=5)


class SemanticScholarConfig(BaseModel):
    """Configuration for Semantic Scholar collector."""

    topics: list[str] = Field(
        default_factory=lambda: ["artificial intelligence", "large language models"]
    )
    max_results: int = Field(default=50)


class GitHubTrendingConfig(BaseModel):
    """Configuration for GitHub Trending collector."""

    languages: list[str] = Field(default_factory=lambda: ["python", ""])
    since: str = Field(default="daily")
    max_items: int = Field(default=30)


class ProductHuntConfig(BaseModel):
    """Configuration for Product Hunt collector."""

    topics: list[str] = Field(default_factory=lambda: ["artificial-intelligence"])
    max_items: int = Field(default=20)


class TavilySearchQuery(BaseModel):
    """A single Tavily search query targeting a specific site/topic."""

    name: str
    query: str


class TavilyConfig(BaseModel):
    """Configuration for Tavily Search collector."""

    searches: list[TavilySearchQuery] = Field(default_factory=list)
    max_results_per_search: int = Field(default=5)
    search_depth: str = Field(default="basic")


class SourceConfig(BaseModel):
    """Top-level source configuration."""

    arxiv: ArxivConfig = Field(default_factory=ArxivConfig)
    hackernews: HackerNewsConfig = Field(default_factory=HackerNewsConfig)
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
    bilibili: BilibiliConfig = Field(default_factory=BilibiliConfig)
    semantic_scholar: SemanticScholarConfig = Field(default_factory=SemanticScholarConfig)
    github_trending: GitHubTrendingConfig = Field(default_factory=GitHubTrendingConfig)
    product_hunt: ProductHuntConfig = Field(default_factory=ProductHuntConfig)
    tavily: TavilyConfig = Field(default_factory=TavilyConfig)
