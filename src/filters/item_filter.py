"""Rule-based filtering: dedup, scoring, and ranking of collected items.

Pipeline: raw items → dedup → score → sort → top-N per category.
No LLM calls — pure heuristic rules for fast, cheap coarse filtering.
"""

from __future__ import annotations

from src.filters.recent_duplicates import RecentDuplicateMatch, penalty_for_matches
from src.logging_config import get_logger
from src.models.source import SourceItem, SourceType

logger = get_logger("filters.item_filter")

# Source types that are "papers"
_PAPER_TYPES = {SourceType.ARXIV_PAPER, SourceType.SEMANTIC_SCHOLAR}
_INDUSTRY_TYPES = {SourceType.TAVILY_SEARCH, SourceType.PRODUCT_HUNT}
_SOCIAL_TYPES = {
    SourceType.HACKER_NEWS, SourceType.YOUTUBE_VIDEO,
    SourceType.BILIBILI_VIDEO, SourceType.GITHUB_TRENDING,
}


class ItemFilter:
    """Dedup, score, and rank collected items."""

    def __init__(
        self,
        paper_limit: int = 40,
        industry_limit: int = 20,
        social_limit: int = 20,
    ):
        self.paper_limit = paper_limit
        self.industry_limit = industry_limit
        self.social_limit = social_limit

    def filter(
        self,
        items: list[SourceItem],
        recent_duplicate_matches: dict[str, list[RecentDuplicateMatch]] | None = None,
    ) -> list[SourceItem]:
        """Apply full filter pipeline: dedup → score → rank → top-N.

        Returns filtered items, grouped in order: papers, industry, social.
        """
        # Step 1: Dedup (arXiv vs Semantic Scholar, etc.)
        deduped = self._dedup(items)

        # Step 2: Split by category
        papers = [i for i in deduped if i.source_type in _PAPER_TYPES]
        industry = [i for i in deduped if i.source_type in _INDUSTRY_TYPES]
        social = [i for i in deduped if i.source_type in _SOCIAL_TYPES]

        # Step 3: Score and sort each category
        papers_ranked = self._rank_papers(papers, recent_duplicate_matches)[:self.paper_limit]
        industry_ranked = self._rank_industry(industry, recent_duplicate_matches)[:self.industry_limit]
        social_ranked = self._rank_social(social, recent_duplicate_matches)[:self.social_limit]

        total_before = len(items)
        total_after = len(papers_ranked) + len(industry_ranked) + len(social_ranked)
        penalized = 0
        if recent_duplicate_matches:
            penalized = sum(1 for item in deduped if item.id in recent_duplicate_matches)
        logger.info(
            "Filter: %d → %d (dedup=%d, papers=%d/%d, industry=%d/%d, social=%d/%d)",
            total_before, total_after, len(deduped),
            len(papers_ranked), len(papers),
            len(industry_ranked), len(industry),
            len(social_ranked), len(social),
        )

        return papers_ranked + industry_ranked + social_ranked

    # --- Dedup ---

    def _dedup(self, items: list[SourceItem]) -> list[SourceItem]:
        """Remove duplicate papers across sources.

        If an arXiv paper also appears in Semantic Scholar, keep the arXiv
        version (richer metadata: categories, full abstract).
        """
        # Build arxiv_id -> SourceItem map for arXiv papers
        arxiv_ids: set[str] = set()
        for item in items:
            if item.source_type == SourceType.ARXIV_PAPER:
                aid = item.metadata.get("arxiv_id", "")
                if aid:
                    arxiv_ids.add(aid)

        # Filter out S2 items that duplicate arXiv items
        deduped: list[SourceItem] = []
        removed = 0
        for item in items:
            if item.source_type == SourceType.SEMANTIC_SCHOLAR:
                s2_arxiv_id = item.metadata.get("arxiv_id", "")
                if s2_arxiv_id and s2_arxiv_id in arxiv_ids:
                    removed += 1
                    continue
            deduped.append(item)

        if removed:
            logger.info("Dedup: removed %d S2 papers already in arXiv", removed)
        return deduped

    # --- Paper scoring ---

    def _rank_papers(self, papers: list[SourceItem]) -> list[SourceItem]:
        """Score and rank papers. Higher = more likely important.

        Signals (for fresh papers, citation_count is usually 0):
        - Cross-listed categories: more categories = broader impact
        - Author count: larger teams often = larger labs / bigger projects
        - Has citation count > 0 (from S2): already getting attention
        - Title keywords: bonus for trending topics
        """
        scored: list[tuple[float, SourceItem]] = []
        for item in papers:
            score = self._score_paper(item)
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]


from src.filters.ranked_item_filter import ItemFilter as ItemFilter

if False:

    def _score_paper(self, item: SourceItem) -> float:
        """Compute importance score for a single paper."""
        score = 0.0
        meta = item.metadata

        # Cross-listed categories (each extra category = +2)
        categories = meta.get("categories", [])
        if len(categories) > 1:
            score += (len(categories) - 1) * 2.0

        # Author count signal (big teams ≥ 5 authors get bonus)
        num_authors = len(item.authors)
        if num_authors >= 10:
            score += 3.0
        elif num_authors >= 5:
            score += 1.5

        # Citation count (from S2, usually 0 for fresh papers)
        citations = meta.get("citation_count", 0)
        if citations > 0:
            score += min(citations, 20)  # Cap at 20

        # Title keyword bonus — trending/important topics
        title_lower = item.title.lower()
        _HOT_KEYWORDS = [
            "llm", "large language model", "gpt", "claude", "gemini",
            "reasoning", "agent", "chain-of-thought", "cot",
            "diffusion", "multimodal", "vision-language",
            "rlhf", "reinforcement learning", "reward model",
            "safety", "alignment", "benchmark",
            "scaling", "efficient", "sparse", "mixture of experts", "moe",
            "world model", "planning", "tool use",
            "code generation", "math", "theorem",
            "transformer", "attention", "architecture",
            "retrieval", "rag", "knowledge",
            "video", "3d", "generation",
            "survey", "benchmark", "evaluation",
        ]
        keyword_hits = sum(1 for kw in _HOT_KEYWORDS if kw in title_lower)
        score += keyword_hits * 1.5

        # Abstract quality signal: very short abstract = likely placeholder
        snippet_len = len(item.content_snippet)
        if snippet_len < 100:
            score -= 3.0

        return score

    # --- Industry scoring ---

    def _rank_industry(self, items: list[SourceItem]) -> list[SourceItem]:
        """Rank industry items by relevance score and votes."""
        scored: list[tuple[float, SourceItem]] = []
        for item in items:
            score = 0.0
            meta = item.metadata

            # Tavily relevance score (0-1)
            tavily_score = meta.get("score", 0)
            if tavily_score:
                score += float(tavily_score) * 10

            # Product Hunt votes
            votes = meta.get("votes_count", 0)
            if votes:
                score += min(votes / 10, 20)  # Cap contribution at 20

            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    # --- Social scoring ---

    def _rank_social(self, items: list[SourceItem]) -> list[SourceItem]:
        """Rank social items by engagement signals."""
        scored: list[tuple[float, SourceItem]] = []
        for item in items:
            score = 0.0
            meta = item.metadata

            # HN score and comments
            hn_score = meta.get("score", 0)
            if hn_score:
                score += min(hn_score / 5, 30)
            comments = meta.get("num_comments", 0)
            if comments:
                score += min(comments / 3, 15)

            # GitHub stars today
            stars_today = meta.get("stars_today", 0)
            if stars_today:
                score += min(stars_today / 50, 20)
            total_stars = meta.get("stars", 0)
            if total_stars:
                score += min(total_stars / 1000, 10)

            # YouTube / Bilibili views
            views = meta.get("view_count", 0) or meta.get("play_count", 0)
            if views:
                score += min(views / 1000, 15)

            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]
