"""Rule-based filtering: same-day dedup plus cross-day duplicate downranking."""

from __future__ import annotations

from src.filters.recent_duplicates import RecentDuplicateMatch, penalty_for_matches
from src.logging_config import get_logger
from src.models.source import SourceItem, SourceType

logger = get_logger("filters.item_filter")

_PAPER_TYPES = {SourceType.ARXIV_PAPER, SourceType.SEMANTIC_SCHOLAR}
_INDUSTRY_TYPES = {SourceType.TAVILY_SEARCH, SourceType.PRODUCT_HUNT}
_SOCIAL_TYPES = {
    SourceType.HACKER_NEWS,
    SourceType.YOUTUBE_VIDEO,
    SourceType.BILIBILI_VIDEO,
    SourceType.GITHUB_TRENDING,
}


class ItemFilter:
    """Dedup, score, and rank collected items."""

    def __init__(
        self,
        paper_limit: int = 40,
        industry_limit: int = 20,
        social_limit: int = 20,
    ) -> None:
        self.paper_limit = paper_limit
        self.industry_limit = industry_limit
        self.social_limit = social_limit

    def filter(
        self,
        items: list[SourceItem],
        recent_duplicate_matches: dict[str, list[RecentDuplicateMatch]] | None = None,
    ) -> list[SourceItem]:
        """Apply same-day dedup, scoring, ranking, and per-category top-N."""
        deduped = self._dedup(items)

        papers = [item for item in deduped if item.source_type in _PAPER_TYPES]
        industry = [item for item in deduped if item.source_type in _INDUSTRY_TYPES]
        social = [item for item in deduped if item.source_type in _SOCIAL_TYPES]

        papers_ranked = self._rank_papers(papers, recent_duplicate_matches)[:self.paper_limit]
        industry_ranked = self._rank_industry(industry, recent_duplicate_matches)[:self.industry_limit]
        social_ranked = self._rank_social(social, recent_duplicate_matches)[:self.social_limit]

        total_before = len(items)
        total_after = len(papers_ranked) + len(industry_ranked) + len(social_ranked)
        penalized = 0
        if recent_duplicate_matches:
            penalized = sum(1 for item in deduped if item.id in recent_duplicate_matches)
        logger.info(
            "Filter: %d -> %d (dedup=%d, penalized=%d, papers=%d/%d, industry=%d/%d, social=%d/%d)",
            total_before,
            total_after,
            len(deduped),
            penalized,
            len(papers_ranked),
            len(papers),
            len(industry_ranked),
            len(industry),
            len(social_ranked),
            len(social),
        )

        return papers_ranked + industry_ranked + social_ranked

    def _dedup(self, items: list[SourceItem]) -> list[SourceItem]:
        """Remove same-day duplicate papers across arXiv and Semantic Scholar."""
        arxiv_ids: set[str] = set()
        for item in items:
            if item.source_type == SourceType.ARXIV_PAPER:
                arxiv_id = item.metadata.get("arxiv_id", "")
                if arxiv_id:
                    arxiv_ids.add(arxiv_id)

        deduped: list[SourceItem] = []
        removed = 0
        for item in items:
            if item.source_type == SourceType.SEMANTIC_SCHOLAR:
                semantic_arxiv_id = item.metadata.get("arxiv_id", "")
                if semantic_arxiv_id and semantic_arxiv_id in arxiv_ids:
                    removed += 1
                    continue
            deduped.append(item)

        if removed:
            logger.info("Dedup: removed %d S2 papers already in arXiv", removed)
        return deduped

    def _rank_papers(
        self,
        papers: list[SourceItem],
        recent_duplicate_matches: dict[str, list[RecentDuplicateMatch]] | None = None,
    ) -> list[SourceItem]:
        scored = [
            (self._score_paper(item, recent_duplicate_matches), item)
            for item in papers
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored]

    def _score_paper(
        self,
        item: SourceItem,
        recent_duplicate_matches: dict[str, list[RecentDuplicateMatch]] | None = None,
    ) -> float:
        score = 0.0
        meta = item.metadata

        categories = meta.get("categories", [])
        if len(categories) > 1:
            score += (len(categories) - 1) * 2.0

        num_authors = len(item.authors)
        if num_authors >= 10:
            score += 3.0
        elif num_authors >= 5:
            score += 1.5

        citations = meta.get("citation_count", 0)
        if citations > 0:
            score += min(citations, 20)

        hot_keywords = [
            "llm",
            "large language model",
            "gpt",
            "claude",
            "gemini",
            "reasoning",
            "agent",
            "chain-of-thought",
            "cot",
            "diffusion",
            "multimodal",
            "vision-language",
            "rlhf",
            "reinforcement learning",
            "reward model",
            "safety",
            "alignment",
            "benchmark",
            "scaling",
            "efficient",
            "sparse",
            "mixture of experts",
            "moe",
            "world model",
            "planning",
            "tool use",
            "code generation",
            "math",
            "theorem",
            "transformer",
            "attention",
            "architecture",
            "retrieval",
            "rag",
            "knowledge",
            "video",
            "3d",
            "generation",
            "survey",
            "evaluation",
        ]
        title_lower = item.title.lower()
        score += sum(1 for keyword in hot_keywords if keyword in title_lower) * 1.5

        if len(item.content_snippet) < 100:
            score -= 3.0

        return score - self._recent_duplicate_penalty(item, recent_duplicate_matches)

    def _rank_industry(
        self,
        items: list[SourceItem],
        recent_duplicate_matches: dict[str, list[RecentDuplicateMatch]] | None = None,
    ) -> list[SourceItem]:
        scored: list[tuple[float, SourceItem]] = []
        for item in items:
            score = 0.0
            meta = item.metadata

            tavily_score = meta.get("score", 0)
            if tavily_score:
                score += float(tavily_score) * 10

            votes = meta.get("votes_count", 0)
            if votes:
                score += min(votes / 10, 20)

            score -= self._recent_duplicate_penalty(item, recent_duplicate_matches)
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored]

    def _rank_social(
        self,
        items: list[SourceItem],
        recent_duplicate_matches: dict[str, list[RecentDuplicateMatch]] | None = None,
    ) -> list[SourceItem]:
        scored: list[tuple[float, SourceItem]] = []
        for item in items:
            score = 0.0
            meta = item.metadata

            hn_score = meta.get("score", 0)
            if hn_score:
                score += min(hn_score / 5, 30)
            comments = meta.get("num_comments", 0)
            if comments:
                score += min(comments / 3, 15)

            stars_today = meta.get("stars_today", 0)
            if stars_today:
                score += min(stars_today / 50, 20)
            total_stars = meta.get("stars", 0)
            if total_stars:
                score += min(total_stars / 1000, 10)

            views = meta.get("view_count", 0) or meta.get("play_count", 0)
            if views:
                score += min(views / 1000, 15)

            score -= self._recent_duplicate_penalty(item, recent_duplicate_matches)
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored]

    def _recent_duplicate_penalty(
        self,
        item: SourceItem,
        recent_duplicate_matches: dict[str, list[RecentDuplicateMatch]] | None,
    ) -> float:
        if not recent_duplicate_matches:
            return 0.0
        return penalty_for_matches(recent_duplicate_matches.get(item.id))
