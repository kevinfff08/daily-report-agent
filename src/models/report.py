"""Data models for generated reports."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class IndexEntry(BaseModel):
    """A single entry in the report index table."""

    index: int
    category: str
    title: str
    source: str
    url: str

    @property
    def index_label(self) -> str:
        return f"[{self.index:03d}]"


class ReportSection(BaseModel):
    """A section of the overview report (grouped by category)."""

    category: str = Field(description="Section category name")
    items_markdown: str = Field(description="Rendered markdown content for this section")
    item_count: int = Field(default=0)


class DailyOverview(BaseModel):
    """Stage 1: Overview report data model."""

    date: date
    summary: str = Field(description="Today's overview paragraph")
    sections: list[ReportSection] = Field(default_factory=list)
    item_index: list[IndexEntry] = Field(default_factory=list)
    total_items: int = Field(default=0)
    generation_time: datetime = Field(default_factory=datetime.now)


class DeepSection(BaseModel):
    """A single section of a deep analysis."""

    heading: str = Field(description="Section heading")
    content: str = Field(description="Section content")


class DeepAnalysis(BaseModel):
    """Deep analysis of a single selected item (Stage 2)."""

    index: int
    title: str
    source_type: str = Field(default="", description="Source type for template selection")
    sections: list[DeepSection] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class DeepDiveReport(BaseModel):
    """Stage 2: Deep dive report data model."""

    date: date
    selected_items: list[int] = Field(description="User-selected item indices")
    analyses: list[DeepAnalysis] = Field(default_factory=list)
    generation_time: datetime = Field(default_factory=datetime.now)
