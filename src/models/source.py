"""Data models for raw collected source items."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Type of data source."""

    ARXIV_PAPER = "arxiv_paper"
    RSS_ARTICLE = "rss_article"
    REDDIT_POST = "reddit_post"
    HACKER_NEWS = "hacker_news"


class SourceItem(BaseModel):
    """A single raw item collected from a data source."""

    id: str = Field(description="Unique identifier for this item")
    source_type: SourceType
    title: str
    url: str
    authors: list[str] = Field(default_factory=list)
    published: datetime
    content_snippet: str = Field(
        default="", description="Abstract, summary, or content excerpt"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Source-specific fields (arXiv categories, Reddit score, etc.)",
    )

    @property
    def source_name(self) -> str:
        """Human-readable source name from metadata or type."""
        return self.metadata.get("source_name", self.source_type.value)
