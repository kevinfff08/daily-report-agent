"""Recent duplicate matching across nearby report dates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlparse

from src.logging_config import get_logger
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore

logger = get_logger("filters.recent_duplicates")

_LOOKBACK_DAYS = 3
_EXACT_PENALTY_BY_DAYS = {1: 8.0, 2: 5.0, 3: 3.0}
_FUZZY_PENALTY_BY_DAYS = {1: 4.0, 2: 2.5, 3: 1.5}
_MAX_TOTAL_PENALTY = 12.0
_TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")

_PAPER_TYPES = {SourceType.ARXIV_PAPER, SourceType.SEMANTIC_SCHOLAR}
_WEB_TYPES = {SourceType.TAVILY_SEARCH, SourceType.PRODUCT_HUNT}


@dataclass(frozen=True)
class HistoricalReportItem:
    """A report item that actually appeared in a previous daily overview body."""

    report_date: date
    index: int
    source_item: SourceItem


@dataclass(frozen=True)
class RecentDuplicateMatch:
    """A single recent duplicate match against a historical report item."""

    history_date: date
    history_index: int
    history_title: str
    match_signal: str
    match_strength: str
    penalty: float


class RecentDuplicateMatcher:
    """Load recent report history and compute duplicate penalties."""

    def __init__(self, store: LocalStore, lookback_days: int = _LOOKBACK_DAYS):
        self.store = store
        self.lookback_days = lookback_days

    def load_recent_history(self, target_date: date) -> list[HistoricalReportItem]:
        """Recover historical SourceItems that entered recent overview bodies."""
        history: list[HistoricalReportItem] = []
        for delta_days in range(1, self.lookback_days + 1):
            report_date = target_date - timedelta(days=delta_days)
            snippets = self.store.load_json(
                self.store.layer_relative_path("reports", report_date, "overview_snippets.json")
            )
            items_index = self.store.load_json(
                self.store.layer_relative_path("reports", report_date, "items_index.json")
            )
            if not isinstance(snippets, list) or not isinstance(items_index, list):
                continue

            index_map: dict[int, SourceItem] = {}
            for row in items_index:
                if not isinstance(row, dict):
                    continue
                try:
                    index = int(row["index"])
                    index_map[index] = SourceItem.model_validate(row["source_item"])
                except Exception as exc:
                    logger.debug("Skipping invalid items_index row for %s: %s", report_date, exc)

            for snippet in snippets:
                if not isinstance(snippet, dict):
                    continue
                try:
                    index = int(snippet["index"])
                except Exception:
                    continue
                source_item = index_map.get(index)
                if source_item is None:
                    continue
                history.append(
                    HistoricalReportItem(
                        report_date=report_date,
                        index=index,
                        source_item=source_item,
                    )
                )

        logger.info(
            "Loaded %d recent historical overview items for %s",
            len(history),
            target_date,
        )
        return history

    def match_items(
        self,
        target_date: date,
        items: list[SourceItem],
        history_items: list[HistoricalReportItem],
    ) -> dict[str, list[RecentDuplicateMatch]]:
        """Match today's items against recent historical overview items."""
        matches_by_item: dict[str, list[RecentDuplicateMatch]] = {}
        for item in items:
            item_matches: list[RecentDuplicateMatch] = []
            for history_item in history_items:
                match = self._match_pair(target_date, item, history_item)
                if match is not None:
                    item_matches.append(match)

            if item_matches:
                item_matches.sort(key=lambda match: (match.history_date, match.history_index), reverse=True)
                matches_by_item[item.id] = item_matches

        logger.info(
            "Recent duplicate matching found %d matched items out of %d candidates",
            len(matches_by_item),
            len(items),
        )
        return matches_by_item

    def penalty_for_item(
        self,
        item: SourceItem,
        matches_by_item: dict[str, list[RecentDuplicateMatch]] | None,
    ) -> float:
        """Compute the capped duplicate penalty for one item."""
        if not matches_by_item:
            return 0.0
        matches = matches_by_item.get(item.id, [])
        if not matches:
            return 0.0
        penalty = sum(match.penalty for match in matches)
        return min(penalty, _MAX_TOTAL_PENALTY)

    def build_debug_payload(
        self,
        target_date: date,
        items: list[SourceItem],
        matches_by_item: dict[str, list[RecentDuplicateMatch]],
    ) -> list[dict[str, object]]:
        """Serialize duplicate matches to a debugging JSON payload."""
        payload: list[dict[str, object]] = []
        for item in items:
            matches = matches_by_item.get(item.id, [])
            if not matches:
                continue
            payload.append(
                {
                    "target_date": target_date.isoformat(),
                    "item_id": item.id,
                    "title": item.title,
                    "source_type": item.source_type.value,
                    "duplicate_penalty": self.penalty_for_item(item, matches_by_item),
                    "matches": [
                        {
                            "history_date": match.history_date.isoformat(),
                            "history_index": match.history_index,
                            "history_title": match.history_title,
                            "match_signal": match.match_signal,
                            "match_strength": match.match_strength,
                            "penalty": match.penalty,
                        }
                        for match in matches
                    ],
                }
            )
        return payload

    def _match_pair(
        self,
        target_date: date,
        item: SourceItem,
        history_item: HistoricalReportItem,
    ) -> RecentDuplicateMatch | None:
        days_ago = (target_date - history_item.report_date).days
        if days_ago < 1 or days_ago > self.lookback_days:
            return None

        current_family = _family_for_type(item.source_type)
        history_family = _family_for_type(history_item.source_item.source_type)
        if current_family != history_family:
            return None

        exact_signal = self._exact_match_signal(item, history_item.source_item)
        if exact_signal is not None:
            return self._build_match(history_item, days_ago, exact_signal, "exact")

        if self._is_fuzzy_title_match(item, history_item.source_item):
            return self._build_match(history_item, days_ago, "title_similarity", "fuzzy")

        return None

    def _build_match(
        self,
        history_item: HistoricalReportItem,
        days_ago: int,
        signal: str,
        strength: str,
    ) -> RecentDuplicateMatch:
        penalty_map = _EXACT_PENALTY_BY_DAYS if strength == "exact" else _FUZZY_PENALTY_BY_DAYS
        return RecentDuplicateMatch(
            history_date=history_item.report_date,
            history_index=history_item.index,
            history_title=history_item.source_item.title,
            match_signal=signal,
            match_strength=strength,
            penalty=penalty_map.get(days_ago, 0.0),
        )

    def _exact_match_signal(self, item: SourceItem, other: SourceItem) -> str | None:
        item_meta = item.metadata
        other_meta = other.metadata

        if item.source_type in _PAPER_TYPES:
            arxiv_id = item_meta.get("arxiv_id")
            other_arxiv_id = other_meta.get("arxiv_id")
            if arxiv_id and other_arxiv_id and arxiv_id == other_arxiv_id:
                return "arxiv_id"
            doi = _normalize_doi(item_meta.get("doi"))
            other_doi = _normalize_doi(other_meta.get("doi"))
            if doi and other_doi and doi == other_doi:
                return "doi"
            return None

        if item.source_type == SourceType.GITHUB_TRENDING:
            repo = _github_repo_key(item)
            other_repo = _github_repo_key(other)
            if repo and other_repo and repo == other_repo:
                return "github_repo"
            url = _normalize_url(item.url)
            other_url = _normalize_url(other.url)
            if url and other_url and url == other_url:
                return "url"
            return None

        if item.source_type == SourceType.HACKER_NEWS:
            story_id = _string_id(item_meta.get("story_id"))
            other_story_id = _string_id(other_meta.get("story_id"))
            if story_id and other_story_id and story_id == other_story_id:
                return "hn_story_id"
            url = _normalize_url(item.url)
            other_url = _normalize_url(other.url)
            if url and other_url and url == other_url:
                return "url"
            return None

        if item.source_type == SourceType.PRODUCT_HUNT:
            post_id = _string_id(item_meta.get("post_id"))
            other_post_id = _string_id(other_meta.get("post_id"))
            if post_id and other_post_id and post_id == other_post_id:
                return "product_hunt_post_id"
            url = _normalize_url(item.url)
            other_url = _normalize_url(other.url)
            if url and other_url and url == other_url:
                return "url"
            return None

        if item.source_type == SourceType.YOUTUBE_VIDEO:
            video_id = _string_id(item_meta.get("video_id"))
            other_video_id = _string_id(other_meta.get("video_id"))
            if video_id and other_video_id and video_id == other_video_id:
                return "youtube_video_id"
            url = _normalize_url(item.url)
            other_url = _normalize_url(other.url)
            if url and other_url and url == other_url:
                return "url"
            return None

        if item.source_type == SourceType.BILIBILI_VIDEO:
            bvid = _string_id(item_meta.get("bvid"))
            other_bvid = _string_id(other_meta.get("bvid"))
            if bvid and other_bvid and bvid == other_bvid:
                return "bilibili_bvid"
            url = _normalize_url(item.url)
            other_url = _normalize_url(other.url)
            if url and other_url and url == other_url:
                return "url"
            return None

        url = _normalize_url(item.url)
        other_url = _normalize_url(other.url)
        if url and other_url and url == other_url:
            return "url"

        return None

    def _is_fuzzy_title_match(self, item: SourceItem, other: SourceItem) -> bool:
        if item.source_type != other.source_type and _family_for_type(item.source_type) != _family_for_type(other.source_type):
            return False

        left_tokens = _title_tokens(item.title)
        right_tokens = _title_tokens(other.title)
        if len(left_tokens) < 2 or len(right_tokens) < 2:
            return False

        overlap = len(left_tokens & right_tokens)
        if overlap < 2:
            return False

        overlap_ratio = overlap / min(len(left_tokens), len(right_tokens))
        jaccard = overlap / len(left_tokens | right_tokens)
        return overlap_ratio >= 0.8 and jaccard >= 0.6


def _family_for_type(source_type: SourceType) -> str:
    if source_type in _PAPER_TYPES:
        return "paper"
    if source_type == SourceType.GITHUB_TRENDING:
        return "github"
    if source_type == SourceType.HACKER_NEWS:
        return "hacker_news"
    if source_type == SourceType.PRODUCT_HUNT:
        return "product_hunt"
    if source_type == SourceType.YOUTUBE_VIDEO:
        return "youtube"
    if source_type == SourceType.BILIBILI_VIDEO:
        return "bilibili"
    if source_type in _WEB_TYPES:
        return "web"
    return source_type.value


def _normalize_doi(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _string_id(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _github_repo_key(item: SourceItem) -> str:
    item_id = item.id.removeprefix("github:")
    if "/" in item_id:
        return item_id.lower()

    path = urlparse(item.url).path.strip("/")
    if path.count("/") >= 1:
        parts = path.split("/")
        return "/".join(parts[:2]).lower()
    return ""


def _normalize_url(raw_url: str) -> str:
    if not raw_url:
        return ""

    parsed = urlparse(raw_url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/").lower()
    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in {"ref", "source"}:
            continue
        query_pairs.append((key_lower, value))
    query_pairs.sort()
    query = "&".join(f"{key}={value}" for key, value in query_pairs)
    normalized = f"{host}{path}"
    if query:
        normalized = f"{normalized}?{query}"
    return normalized


def _title_tokens(title: str) -> set[str]:
    tokens = {match.group(0).lower() for match in _TITLE_TOKEN_RE.finditer(title)}
    for chunk in _CJK_RE.findall(title):
        if len(chunk) == 1:
            tokens.add(chunk)
            continue
        for idx in range(len(chunk) - 1):
            tokens.add(chunk[idx:idx + 2])
    return tokens


def penalty_for_matches(matches: list[RecentDuplicateMatch] | None) -> float:
    """Compute a capped duplicate penalty from raw match rows."""
    if not matches:
        return 0.0
    return min(sum(match.penalty for match in matches), _MAX_TOTAL_PENALTY)
