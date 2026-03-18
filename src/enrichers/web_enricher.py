"""Web enricher: fetches full page content and supplementary search results via Tavily."""

from __future__ import annotations

import os

import httpx

from src.logging_config import get_logger
from src.models.source import SourceItem

logger = get_logger("enrichers.web")

TAVILY_EXTRACT_API = "https://api.tavily.com/extract"
TAVILY_SEARCH_API = "https://api.tavily.com/search"

# Max chars for extracted page content
_MAX_EXTRACT_CHARS = 15_000
# Max chars per supplementary search result
_MAX_SEARCH_RESULT_CHARS = 3_000
# Number of supplementary search results
_SEARCH_MAX_RESULTS = 3


class WebEnricher:
    """Enriches web items by extracting full page content and searching for related info."""

    async def enrich(self, item: SourceItem, *, supplementary_search: bool = False) -> str:
        """Enrich a web-based item with full content and optional related context.

        Args:
            item: The source item to enrich.
            supplementary_search: If True, also search for related articles/coverage.

        Returns:
            Enriched text combining page content and search results, or empty string.
        """
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            logger.warning("TAVILY_API_KEY not set, cannot enrich web content")
            return ""

        parts: list[str] = []

        # Strategy A: Extract full page content from the item URL
        extracted = await self._extract_page(api_key, item.url)
        if extracted:
            parts.append(f"=== 原文内容 ===\n{extracted}")
            logger.info("Extracted %d chars from %s", len(extracted), item.url)
        else:
            logger.debug("Page extraction failed/empty for %s", item.url)

        # Strategy B: Supplementary search for related coverage
        if supplementary_search:
            search_results = await self._search_related(api_key, item.title)
            if search_results:
                parts.append(f"=== 相关报道与评测 ===\n{search_results}")
                logger.info("Found supplementary context for: %s", item.title)

        return "\n\n".join(parts)

    async def _extract_page(self, api_key: str, url: str) -> str:
        """Extract full text content from a URL using Tavily Extract API."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    TAVILY_EXTRACT_API,
                    json={
                        "api_key": api_key,
                        "urls": [url],
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            if results and results[0].get("raw_content"):
                return results[0]["raw_content"][:_MAX_EXTRACT_CHARS]

        except Exception as e:
            logger.debug("Tavily extract failed for %s: %s", url, e)

        return ""

    async def _search_related(self, api_key: str, title: str) -> str:
        """Search for related articles and coverage about the item."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    TAVILY_SEARCH_API,
                    json={
                        "api_key": api_key,
                        "query": title,
                        "search_depth": "advanced",
                        "max_results": _SEARCH_MAX_RESULTS,
                        "include_raw_content": True,
                        "include_answer": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            parts: list[str] = []
            for r in data.get("results", []):
                r_title = r.get("title", "")
                r_url = r.get("url", "")
                r_content = r.get("raw_content") or r.get("content", "")
                if r_content:
                    parts.append(
                        f"来源: {r_title}\nURL: {r_url}\n{r_content[:_MAX_SEARCH_RESULT_CHARS]}"
                    )

            return "\n\n---\n\n".join(parts) if parts else ""

        except Exception as e:
            logger.debug("Tavily search failed for '%s': %s", title, e)

        return ""
