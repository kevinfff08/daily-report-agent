"""Registry manager for auto-registering deep-dive results and searching history."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Callable, Literal

from src.llm import LLMClient
from src.logging_config import get_logger
from src.models.registry import RegistryAttribute, RegistryEntry
from src.models.report import DeepAnalysis, DeepDiveReport, OverviewSnippet
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore
from src.storage.registry_store import RegistryStore
from src.utils.overview_snippets import extract_overview_snippets

logger = get_logger("registry.manager")

_ATTRIBUTE_FALLBACKS: dict[SourceType, RegistryAttribute] = {
    SourceType.ARXIV_PAPER: RegistryAttribute.PAPER,
    SourceType.SEMANTIC_SCHOLAR: RegistryAttribute.PAPER,
    SourceType.PRODUCT_HUNT: RegistryAttribute.PRODUCT,
    SourceType.TAVILY_SEARCH: RegistryAttribute.PRODUCT,
    SourceType.YOUTUBE_VIDEO: RegistryAttribute.PRODUCT,
    SourceType.BILIBILI_VIDEO: RegistryAttribute.PRODUCT,
    SourceType.GITHUB_TRENDING: RegistryAttribute.PROJECT,
    SourceType.HACKER_NEWS: RegistryAttribute.PROJECT,
}
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")
_MatchMethod = Literal["keywords", "summary", "llm"]


class DeepDiveRegistryManager:
    """Builds, persists, and searches deep-dive registry entries."""

    def __init__(
        self,
        llm: LLMClient,
        store: RegistryStore | None = None,
        local_store: LocalStore | None = None,
    ):
        self.llm = llm
        self.store = store or RegistryStore()
        self.local_store = local_store

    def register_from_deep_dive(
        self,
        target_date: date,
        report: DeepDiveReport,
        items_index: list[dict],
    ) -> int:
        """Register deep-dive analyses into the long-term registry."""
        index_map = self._build_index_map(items_index)
        overview_snippets = self._load_overview_snippets(target_date)
        entries: list[RegistryEntry] = []

        for analysis in report.analyses:
            item = index_map.get(analysis.index)
            if item is None:
                logger.warning("Skipping registry entry for missing item index [%03d]", analysis.index)
                continue

            keywords, attribute = self._extract_metadata(item, analysis)
            summary_markdown = self._resolve_summary_markdown(analysis.index, item, overview_snippets)
            entry = RegistryEntry(
                date=target_date,
                record_id=f"{target_date.strftime('%Y%m%d')}-{analysis.index:03d}",
                title=analysis.title,
                keywords=keywords,
                attribute=attribute,
                summary_ref=f"SUM-{target_date.strftime('%Y%m%d')}-{analysis.index:03d}",
                summary_markdown=summary_markdown,
                source_index=analysis.index,
            )
            entries.append(entry)

        if not entries:
            return 0

        self.store.upsert_month_entries(target_date, entries)
        return len(entries)

    def find_entries(self, query: str, limit: int = 10) -> tuple[_MatchMethod, list[RegistryEntry]]:
        """Find related entries using keyword, summary, then LLM fallback."""
        normalized_query = query.strip()
        if not normalized_query:
            return "keywords", []

        entries = self.store.load_all_entries()
        if not entries:
            return "keywords", []

        keyword_matches = self._score_entries(entries, normalized_query, lambda entry: " ".join(entry.keywords))
        if keyword_matches:
            return "keywords", keyword_matches[:limit]

        summary_matches = self._score_entries(entries, normalized_query, lambda entry: entry.summary_markdown)
        if summary_matches:
            return "summary", summary_matches[:limit]

        return "llm", self._llm_match_entries(entries, normalized_query, limit)

    @staticmethod
    def _build_index_map(items_index: list[dict]) -> dict[int, SourceItem]:
        index_map: dict[int, SourceItem] = {}
        for entry in items_index:
            idx = entry.get("index")
            if not isinstance(idx, int):
                continue
            try:
                index_map[idx] = SourceItem.model_validate(entry["source_item"])
            except Exception as exc:
                logger.warning("Skipping invalid item index [%s]: %s", idx, exc)
        return index_map

    def _load_overview_snippets(self, target_date: date) -> dict[int, OverviewSnippet]:
        snippets: list[OverviewSnippet] = []
        if self.local_store is not None:
            raw = self.local_store.load_json(
                self.local_store.layer_relative_path("reports", target_date, "overview_snippets.json")
            )
            if isinstance(raw, list):
                for item in raw:
                    try:
                        snippets.append(OverviewSnippet.model_validate(item))
                    except Exception as exc:
                        logger.warning("Skipping invalid overview snippet: %s", exc)

        if not snippets:
            if self.local_store is not None:
                output_path = self.local_store.output_path(target_date, "daily_report.md")
            else:
                output_path = Path("output") / LocalStore.relative_date_dir(target_date) / "daily_report.md"
            if output_path.exists():
                snippets = extract_overview_snippets(output_path.read_text(encoding="utf-8"))

        return {snippet.index: snippet for snippet in snippets}

    def _resolve_summary_markdown(
        self,
        index: int,
        item: SourceItem,
        overview_snippets: dict[int, OverviewSnippet],
    ) -> str:
        snippet = overview_snippets.get(index)
        if snippet is not None and snippet.summary_markdown.strip():
            return snippet.summary_markdown.strip()

        fallback_parts: list[str] = []
        if item.url:
            fallback_parts.append(f"**链接：** {item.url}")
        if item.content_snippet.strip():
            fallback_parts.append(item.content_snippet.strip())
        if not fallback_parts:
            fallback_parts.append("（该条目未进入当日简版报告正文，暂无可复用摘要。）")
        return "\n\n".join(fallback_parts)

    def _extract_metadata(
        self,
        item: SourceItem,
        analysis: DeepAnalysis,
    ) -> tuple[list[str], RegistryAttribute]:
        fallback_attribute = _ATTRIBUTE_FALLBACKS[item.source_type]
        summary = self._build_deep_dive_summary(analysis)
        try:
            result = self.llm.generate_json_with_template(
                "registry_metadata",
                {
                    "title": item.title,
                    "source": item.source_name,
                    "source_type": item.source_type.value,
                    "summary": summary,
                    "references": "\n".join(analysis.references[:5]) or "(none)",
                },
                max_tokens=600,
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("Registry metadata extraction failed for [%03d]: %s", analysis.index, exc)
            return [], fallback_attribute

        if not isinstance(result, dict):
            logger.warning("Registry metadata extraction returned non-dict for [%03d]", analysis.index)
            return [], fallback_attribute

        keywords_raw = result.get("keywords", [])
        if isinstance(keywords_raw, list):
            keywords = [str(keyword).strip() for keyword in keywords_raw if str(keyword).strip()]
        else:
            keywords = []

        attribute_raw = str(result.get("attribute", "")).strip()
        try:
            attribute = RegistryAttribute(attribute_raw)
        except ValueError:
            attribute = fallback_attribute

        return keywords[:5], attribute

    @staticmethod
    def _build_deep_dive_summary(analysis: DeepAnalysis) -> str:
        chunks: list[str] = []
        for section in analysis.sections[:3]:
            content = section.content.strip()
            if not content:
                continue
            chunks.append(f"{section.heading}\n{content[:600]}")
        return "\n\n".join(chunks)

    def _score_entries(
        self,
        entries: list[RegistryEntry],
        query: str,
        text_getter: Callable[[RegistryEntry], str],
    ) -> list[RegistryEntry]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored: list[tuple[int, RegistryEntry]] = []
        for entry in entries:
            candidate_tokens = self._tokenize(text_getter(entry))
            score = self._token_overlap(query_tokens, candidate_tokens)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda item: (-item[0], -item[1].date.toordinal(), item[1].record_id))
        return [entry for _, entry in scored]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        normalized = text.lower().strip()
        tokens: list[str] = []
        for part in _TOKEN_RE.findall(normalized):
            if not part:
                continue
            if all("\u4e00" <= char <= "\u9fff" for char in part):
                if len(part) == 1:
                    tokens.append(part)
                else:
                    tokens.extend(part[idx:idx + 2] for idx in range(len(part) - 1))
            else:
                tokens.append(part)
        return tokens

    @staticmethod
    def _token_overlap(query_tokens: list[str], candidate_tokens: list[str]) -> int:
        query_counter = Counter(query_tokens)
        candidate_counter = Counter(candidate_tokens)
        overlap = 0
        for token, count in query_counter.items():
            overlap += min(count, candidate_counter.get(token, 0))
        return overlap

    def _llm_match_entries(self, entries: list[RegistryEntry], query: str, limit: int) -> list[RegistryEntry]:
        records_payload = [
            {
                "file_name": self.store.resolve_month_path(entry.date).name,
                "date": entry.date.isoformat(),
                "record_id": entry.record_id,
                "title": entry.title,
                "keywords": entry.keywords,
                "summary": entry.summary_markdown,
            }
            for entry in entries
        ]

        try:
            result = self.llm.generate_json_with_template(
                "registry_match",
                {
                    "query": query,
                    "limit": limit,
                    "records_json": json.dumps(records_payload, ensure_ascii=False, indent=2),
                },
                max_tokens=1200,
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("Registry LLM matching failed: %s", exc)
            return []

        if not isinstance(result, dict):
            logger.warning("Registry LLM matching returned non-dict result")
            return []

        record_ids = result.get("record_ids", [])
        if not isinstance(record_ids, list):
            return []

        by_id = {entry.record_id: entry for entry in entries}
        matches: list[RegistryEntry] = []
        for record_id in record_ids:
            candidate = by_id.get(str(record_id).strip())
            if candidate is not None and candidate not in matches:
                matches.append(candidate)
            if len(matches) >= limit:
                break
        return matches
