"""Collector for AI company blogs and news via Tavily Search API."""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timezone

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType

TAVILY_API = "https://api.tavily.com/search"


class TavilyCollector(BaseCollector):
    """Collects recent blog posts and news via Tavily site-specific searches."""

    source_name = "tavily"

    async def collect(self, target_date: date) -> list[SourceItem]:
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            self.logger.warning("TAVILY_API_KEY not set, skipping Tavily collection")
            return []

        searches: list[dict] = self.config.get("searches", [])
        max_per_search: int = self.config.get("max_results_per_search", 5)
        search_depth: str = self.config.get("search_depth", "basic")

        if not searches:
            self.logger.info("No Tavily searches configured")
            return []

        all_items: list[SourceItem] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for search_cfg in searches:
                name = search_cfg.get("name", "Unknown")
                query = search_cfg.get("query", "")
                if not query:
                    continue

                try:
                    items = await self._search(
                        client, api_key, name, query,
                        max_per_search, search_depth,
                    )
                    for item in items:
                        url = item.url
                        if url not in seen_urls:
                            seen_urls.add(url)
                            all_items.append(item)
                except Exception as e:
                    self.logger.warning("Tavily search error for '%s': %s", name, e)

        self.logger.info("Tavily total: %d results from %d searches", len(all_items), len(searches))
        return all_items

    async def _search(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        name: str,
        query: str,
        max_results: int,
        search_depth: str,
    ) -> list[SourceItem]:
        """Execute a single Tavily search."""
        # Tavily requires actual search terms alongside site: operators
        # If query is only site: operators, append "latest news" as search terms
        effective_query = query
        stripped = query.strip()
        # Check if query is only site: clauses (no real search terms)
        parts = stripped.split()
        if all(p.startswith("site:") or p == "OR" for p in parts):
            effective_query = f"{stripped} latest news updates"

        payload = {
            "api_key": api_key,
            "query": effective_query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "days": 3,  # Look back 3 days
        }

        resp = await client.post(TAVILY_API, json=payload)
        resp.raise_for_status()
        data = resp.json()

        results: list[SourceItem] = []
        for r in data.get("results", []):
            url = r.get("url", "")
            if not url:
                continue

            # Generate stable ID from URL
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]

            # Tavily doesn't always return published dates
            published = datetime.now(tz=timezone.utc)
            if r.get("published_date"):
                try:
                    published = datetime.fromisoformat(
                        r["published_date"].replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            results.append(SourceItem(
                id=f"tavily:{url_hash}",
                source_type=SourceType.TAVILY_SEARCH,
                title=r.get("title", ""),
                url=url,
                authors=[],
                published=published,
                content_snippet=r.get("content", "")[:1000],
                metadata={
                    "search_name": name,
                    "search_query": query,
                    "score": r.get("score", 0),
                    "source_name": name,
                },
            ))

        return results
