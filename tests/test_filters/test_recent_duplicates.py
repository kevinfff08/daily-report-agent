"""Tests for recent cross-day duplicate matching and penalty scoring."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from src.filters import ItemFilter, RecentDuplicateMatcher
from src.filters.recent_duplicates import HistoricalReportItem
from src.models.source import SourceItem, SourceType
from src.storage.local_store import LocalStore


@contextmanager
def _workspace_data_dir() -> Path:
    base_dir = Path(".tmp-test-filters")
    base_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = base_dir / f"recent-duplicates-{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _make_item(
    *,
    item_id: str,
    source_type: SourceType,
    title: str,
    url: str,
    published: datetime,
    snippet: str = "Detailed summary for ranking purposes.",
    metadata: dict | None = None,
    authors: list[str] | None = None,
) -> SourceItem:
    return SourceItem(
        id=item_id,
        source_type=source_type,
        title=title,
        url=url,
        authors=authors or ["Author"],
        published=published,
        content_snippet=snippet,
        metadata=metadata or {},
    )


def test_load_recent_history_rehydrates_report_body_items(sample_date, sample_github_trending_item) -> None:
    with _workspace_data_dir() as temp_dir:
        store = LocalStore(data_dir=temp_dir / "data")
        matcher = RecentDuplicateMatcher(store)
        history_date = sample_date - timedelta(days=1)
        store.save_json(
            f"reports/{history_date.isoformat()}/items_index.json",
            [
                {"index": 1, "source_item": sample_github_trending_item.model_dump(mode="json")},
                {"index": 2, "source_item": sample_github_trending_item.model_dump(mode="json")},
            ],
        )
        store.save_json(
            f"reports/{history_date.isoformat()}/overview_snippets.json",
            [
                {"index": 2, "title": sample_github_trending_item.title, "summary_markdown": "Kept in report"},
            ],
        )

        history_items = matcher.load_recent_history(sample_date)

        assert len(history_items) == 1
        assert history_items[0].report_date == history_date
        assert history_items[0].index == 2
        assert history_items[0].source_item.id == sample_github_trending_item.id


def test_match_items_exact_identifiers(sample_date, sample_hn_item) -> None:
    matcher = RecentDuplicateMatcher(store=None)  # type: ignore[arg-type]
    today_item = sample_hn_item.model_copy(
        update={
            "title": "Show HN: Open-source LLM evaluation toolkit",
            "published": sample_hn_item.published + timedelta(days=1),
        }
    )
    history_item = HistoricalReportItem(
        report_date=sample_date - timedelta(days=1),
        index=7,
        source_item=sample_hn_item,
    )

    matches = matcher.match_items(sample_date, [today_item], [history_item])

    assert today_item.id in matches
    assert matches[today_item.id][0].match_signal == "hn_story_id"
    assert matches[today_item.id][0].match_strength == "exact"
    assert matches[today_item.id][0].penalty == 8.0


def test_match_items_fuzzy_title_match_within_same_family(sample_date) -> None:
    matcher = RecentDuplicateMatcher(store=None)  # type: ignore[arg-type]
    history_source = _make_item(
        item_id="arxiv:2603.20001",
        source_type=SourceType.ARXIV_PAPER,
        title="Mixture of Experts for Efficient LLM Reasoning",
        url="https://arxiv.org/abs/2603.20001",
        published=datetime(2026, 3, 26, tzinfo=timezone.utc),
        metadata={"arxiv_id": "2603.20001"},
    )
    today_item = _make_item(
        item_id="s2:paper-rewrite",
        source_type=SourceType.SEMANTIC_SCHOLAR,
        title="Efficient LLM Reasoning with Mixture of Experts",
        url="https://www.semanticscholar.org/paper/paper-rewrite",
        published=datetime(2026, 3, 27, tzinfo=timezone.utc),
        metadata={"paper_id": "paper-rewrite"},
    )
    history_item = HistoricalReportItem(
        report_date=sample_date - timedelta(days=1),
        index=3,
        source_item=history_source,
    )

    matches = matcher.match_items(sample_date, [today_item], [history_item])

    assert matches[today_item.id][0].match_signal == "title_similarity"
    assert matches[today_item.id][0].match_strength == "fuzzy"


def test_match_items_does_not_fuzzy_match_across_families(sample_date) -> None:
    matcher = RecentDuplicateMatcher(store=None)  # type: ignore[arg-type]
    history_item = HistoricalReportItem(
        report_date=sample_date - timedelta(days=1),
        index=1,
        source_item=_make_item(
            item_id="tavily:company-blog",
            source_type=SourceType.TAVILY_SEARCH,
            title="Agent workflow benchmark for coding IDEs",
            url="https://example.com/blog/agent-workflow",
            published=datetime(2026, 3, 26, tzinfo=timezone.utc),
            metadata={"score": 0.9},
        ),
    )
    today_item = _make_item(
        item_id="github:owner/agent-workflow",
        source_type=SourceType.GITHUB_TRENDING,
        title="Agent workflow benchmark for coding IDEs",
        url="https://github.com/owner/agent-workflow",
        published=datetime(2026, 3, 27, tzinfo=timezone.utc),
        metadata={"stars_today": 80, "stars": 1200},
    )

    matches = matcher.match_items(sample_date, [today_item], [history_item])

    assert matches == {}


def test_penalty_caps_and_item_filter_downranks_recent_duplicates(sample_date) -> None:
    matcher = RecentDuplicateMatcher(store=None)  # type: ignore[arg-type]
    item_filter = ItemFilter()
    duplicate_item = _make_item(
        item_id="github:owner/duplicate-project",
        source_type=SourceType.GITHUB_TRENDING,
        title="owner/duplicate-project",
        url="https://github.com/owner/duplicate-project",
        published=datetime(2026, 3, 27, tzinfo=timezone.utc),
        metadata={"stars_today": 200, "stars": 5000},
    )
    fresh_item = _make_item(
        item_id="github:owner/fresh-project",
        source_type=SourceType.GITHUB_TRENDING,
        title="owner/fresh-project",
        url="https://github.com/owner/fresh-project",
        published=datetime(2026, 3, 27, tzinfo=timezone.utc),
        metadata={"stars_today": 120, "stars": 3000},
    )
    history_items = [
        HistoricalReportItem(
            report_date=sample_date - timedelta(days=days_ago),
            index=days_ago,
            source_item=_make_item(
                item_id=f"github:owner/duplicate-project-{days_ago}",
                source_type=SourceType.GITHUB_TRENDING,
                title="owner/duplicate-project",
                url="https://github.com/owner/duplicate-project",
                published=datetime(2026, 3, 27 - days_ago, tzinfo=timezone.utc),
                metadata={"stars_today": 50, "stars": 1000},
            ),
        )
        for days_ago in (1, 2, 3)
    ]

    recent_duplicate_matches = matcher.match_items(sample_date, [duplicate_item, fresh_item], history_items)
    penalty = matcher.penalty_for_item(duplicate_item, recent_duplicate_matches)
    ranked_items = item_filter.filter(
        [duplicate_item, fresh_item],
        recent_duplicate_matches=recent_duplicate_matches,
    )

    assert penalty == 12.0
    assert recent_duplicate_matches.get(fresh_item.id) is None
    assert ranked_items[0].id == fresh_item.id
