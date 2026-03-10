"""Data models for source configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RSSFeedConfig(BaseModel):
    """Configuration for a single RSS feed."""

    name: str
    url: str
    category: str = Field(default="news", description="industry / news / academic")


class ArxivConfig(BaseModel):
    """Configuration for arXiv collector."""

    categories: list[str] = Field(default_factory=lambda: ["cs.AI", "cs.CL", "cs.CV", "cs.LG"])
    max_results_per_category: int = Field(default=50)


class RSSConfig(BaseModel):
    """Configuration for RSS collector."""

    feeds: list[RSSFeedConfig] = Field(default_factory=list)


class RedditConfig(BaseModel):
    """Configuration for Reddit collector."""

    subreddits: list[str] = Field(default_factory=lambda: ["MachineLearning", "LocalLLaMA"])
    sort: str = Field(default="hot")
    time_filter: str = Field(default="day")
    limit: int = Field(default=25)


class HackerNewsConfig(BaseModel):
    """Configuration for Hacker News collector."""

    min_score: int = Field(default=50)
    max_items: int = Field(default=30)
    keywords: list[str] = Field(
        default_factory=lambda: ["AI", "LLM", "machine learning", "neural", "GPT", "Claude", "transformer"]
    )


class SourceConfig(BaseModel):
    """Top-level source configuration."""

    arxiv: ArxivConfig = Field(default_factory=ArxivConfig)
    rss: RSSConfig = Field(default_factory=RSSConfig)
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    hackernews: HackerNewsConfig = Field(default_factory=HackerNewsConfig)
