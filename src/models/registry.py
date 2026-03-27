"""Data models for the monthly deep-dive registry."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


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

    @classmethod
    def ordered(cls) -> list["InterestStatus"]:
        """Return statuses in canonical display order."""
        return [cls.STAR, cls.QUESTION, cls.CHECK]

    @classmethod
    def parse_symbols(cls, value: str) -> list["InterestStatus"]:
        """Leniently parse one or more symbols from a free-form cell."""
        normalized = value.strip()
        if not normalized:
            return []

        found: list[InterestStatus] = []
        for status in cls.ordered():
            if status.value in normalized:
                found.append(status)
        return found

    @classmethod
    def format_symbols(cls, statuses: list["InterestStatus"]) -> str:
        """Render statuses into the canonical Markdown cell text."""
        ordered_statuses = [status for status in cls.ordered() if status in statuses]
        return " ".join(status.value for status in ordered_statuses)


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
    interest_statuses: list[InterestStatus] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_interest_status(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        if "interest_statuses" in payload:
            return payload

        legacy_value = payload.pop("interest_status", None)
        if legacy_value is not None:
            payload["interest_statuses"] = legacy_value
        return payload

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

    @field_validator("interest_statuses", mode="before")
    @classmethod
    def _validate_interest_statuses(cls, value: Any) -> list[InterestStatus]:
        if value is None:
            return []
        if isinstance(value, InterestStatus):
            return [] if value == InterestStatus.NONE else [value]
        if isinstance(value, str):
            return InterestStatus.parse_symbols(value)
        if isinstance(value, (list, tuple, set)):
            parsed: list[InterestStatus] = []
            for item in value:
                if isinstance(item, InterestStatus):
                    if item != InterestStatus.NONE and item not in parsed:
                        parsed.append(item)
                    continue
                for status in InterestStatus.parse_symbols(str(item)):
                    if status not in parsed:
                        parsed.append(status)
            return [status for status in InterestStatus.ordered() if status in parsed]
        return []

    @property
    def month_key(self) -> str:
        """Return the YYYY-MM partition for this entry."""
        return self.date.strftime("%Y-%m")

    @property
    def interest_status_display(self) -> str:
        """Return the canonical status cell text."""
        return InterestStatus.format_symbols(self.interest_statuses)

    def has_interest_status(self, status: InterestStatus) -> bool:
        """Check whether a status is present on the row."""
        return status in self.interest_statuses
