"""Content enrichment for deep dive analysis.

Routes items to the appropriate enricher based on source type.
"""

from __future__ import annotations

from src.enrichers.paper_enricher import PaperEnricher
from src.enrichers.web_enricher import WebEnricher
from src.logging_config import get_logger
from src.models.source import SourceItem, SourceType

logger = get_logger("enrichers")

_paper_enricher = PaperEnricher()
_web_enricher = WebEnricher()

# Source types that use paper enrichment (PDF full text)
_PAPER_TYPES = {SourceType.ARXIV_PAPER, SourceType.SEMANTIC_SCHOLAR}

# Source types that use web enrichment (extract + search)
_WEB_SEARCH_TYPES = {SourceType.TAVILY_SEARCH, SourceType.PRODUCT_HUNT}

# Source types that use web enrichment (extract only, no supplementary search)
_WEB_EXTRACT_TYPES = {SourceType.HACKER_NEWS, SourceType.GITHUB_TRENDING}

# Source types that cannot be enriched (video content)
_SKIP_TYPES = {SourceType.YOUTUBE_VIDEO, SourceType.BILIBILI_VIDEO}


async def enrich_item(item: SourceItem, paper_max_chars: int | None = None) -> str:
    """Enrich item content for deep dive analysis.

    Returns enriched text to pass to LLM. Falls back to content_snippet on failure.
    """
    if item.source_type in _PAPER_TYPES:
        paper_enricher = _paper_enricher if paper_max_chars is None else PaperEnricher(max_chars=paper_max_chars)
        enriched = await paper_enricher.enrich(item)
        if enriched:
            return enriched

    elif item.source_type in _WEB_SEARCH_TYPES:
        enriched = await _web_enricher.enrich(item, supplementary_search=True)
        if enriched:
            return enriched

    elif item.source_type in _WEB_EXTRACT_TYPES:
        enriched = await _web_enricher.enrich(item, supplementary_search=False)
        if enriched:
            return enriched

    # Fallback: use original snippet
    logger.debug("Using original content_snippet for [%s] %s", item.source_type.value, item.title)
    return item.content_snippet


__all__ = ["enrich_item"]
