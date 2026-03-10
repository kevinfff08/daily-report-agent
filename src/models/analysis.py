"""Data models for analyzed items."""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, Field

from src.models.source import SourceItem, SourceType


class PaperAnalysis(BaseModel):
    """Structured analysis of an academic paper."""

    problem_definition: str = Field(description="What problem does this paper solve? (2-3 sentences)")
    method_overview: str = Field(description="Core technical approach and innovation (3-5 sentences)")
    main_results: str = Field(description="Key experimental results and benchmarks (2-3 sentences)")
    related_work: str = Field(description="Relationship to prior/concurrent work (1-2 sentences)")
    potential_impact: str = Field(description="Potential impact on the field (1-2 sentences)")


class IndustryAnalysis(BaseModel):
    """Structured analysis of an industry announcement/update."""

    release_summary: str = Field(description="What was released and its core capabilities (2-3 sentences)")
    technical_details: str = Field(description="Technical architecture/methods disclosed (3-5 sentences)")
    competitive_comparison: str = Field(description="Comparison with competitors/alternatives (2-3 sentences)")
    industry_impact: str = Field(description="Potential impact on the industry (1-2 sentences)")


class SocialAnalysis(BaseModel):
    """Structured analysis of a social media discussion/post."""

    discussion_core: str = Field(description="What is being discussed (2-3 sentences)")
    key_viewpoints: str = Field(description="Major viewpoints and disagreements (3-5 sentences)")
    technical_substance: str = Field(description="Underlying technical facts (2-3 sentences)")


# Union type for analysis field
AnalysisUnion = Union[PaperAnalysis, IndustryAnalysis, SocialAnalysis]


class AnalyzedItem(BaseModel):
    """An analyzed item with numbered index for the report."""

    index: int = Field(description="Report item number, e.g. 1 for [001]")
    source_item: SourceItem
    source_type: SourceType
    category: str = Field(description="Report category: 论文 / 业界动态 / 社区热点")
    analysis: PaperAnalysis | IndustryAnalysis | SocialAnalysis = Field(
        discriminator=None
    )
    importance_note: str = Field(default="", description="Optional importance note")

    @property
    def index_label(self) -> str:
        """Formatted index label like [001]."""
        return f"[{self.index:03d}]"
