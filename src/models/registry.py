"""Data models for the monthly deep-dive registry."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class RegistryAttribute(str, Enum):
    """High-level item attribute shown in the registry."""

    PAPER = "论文"
    PRODUCT = "产品"
    PROJECT = "项目"


class InterestStatus(str, Enum):
    """User-maintained interest status."""

    NONE = ""
    STAR = "*"
    QUESTION = "?"
    CHECK = "✓"

    @classmethod
    def from_symbol(cls, value: str) -> "InterestStatus":
        """Parse a registry status symbol."""
        normalized = value.strip()
        for status in cls:
            if status.value == normalized:
                return status
        raise ValueError(f"Unsupported interest status symbol: {value}")


class RegistryEntry(BaseModel):
    """A single registry row."""

    date: date
    record_id: str = Field(description="Stable ID like 20260325-001")
    title: str
    keywords: list[str] = Field(default_factory=list)
    attribute: RegistryAttribute
    summary_ref: str = Field(description="Stable summary anchor like SUM-20260325-001")
    summary_markdown: str = Field(default="", description="Rendered summary stored in appendix")
    source_index: int | None = Field(default=None, description="Original deep-dive index")
    interest_status: InterestStatus = Field(default=InterestStatus.NONE)

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, keywords: list[str]) -> list[str]:
        cleaned: list[str] = []
        for keyword in keywords:
            text = " ".join(keyword.replace("\n", " ").split()).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned[:5]

    @field_validator("title")
    @classmethod
    def _validate_title(cls, title: str) -> str:
        return " ".join(title.replace("\n", " ").split()).strip()

    @field_validator("summary_ref")
    @classmethod
    def _validate_summary_ref(cls, summary_ref: str) -> str:
        normalized = " ".join(summary_ref.split()).strip()
        if not normalized:
            raise ValueError("Registry entry must include a summary reference")
        return normalized

    @field_validator("summary_markdown")
    @classmethod
    def _validate_summary_markdown(cls, summary_markdown: str) -> str:
        return summary_markdown.strip()

    @property
    def month_key(self) -> str:
        """Return the YYYY-MM partition for this entry."""
        return self.date.strftime("%Y-%m")
