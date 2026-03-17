"""Collector for academic papers via Semantic Scholar API."""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType

S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,abstract,authors,year,publicationDate,citationCount,url,externalIds"


class SemanticScholarCollector(BaseCollector):
    """Collects recent AI papers from Semantic Scholar."""

    source_name = "semantic_scholar"

    async def collect(self, target_date: date) -> list[SourceItem]:
        topics: list[str] = self.config.get("topics", [])
        max_results: int = self.config.get("max_results", 50)
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

        if not topics:
            self.logger.info("No Semantic Scholar topics configured")
            return []

        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key

        all_items: list[SourceItem] = []
        seen_ids: set[str] = set()
        per_topic = max(max_results // len(topics), 10)

        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            for idx, topic in enumerate(topics):
                # Retry with exponential backoff for rate limiting
                for attempt in range(4):
                    try:
                        items = await self._search_topic(
                            client, topic, per_topic, target_date,
                        )
                        for item in items:
                            if item.id not in seen_ids:
                                seen_ids.add(item.id)
                                all_items.append(item)
                        break  # Success, exit retry loop
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429 and attempt < 3:
                            wait = 5 * (2 ** attempt)  # 5, 10, 20 seconds
                            self.logger.info("S2 rate limited for '%s', retrying in %ds (attempt %d/4)...", topic, wait, attempt + 1)
                            await asyncio.sleep(wait)
                        else:
                            self.logger.warning("S2 search error for '%s': %s", topic, e)
                            break
                    except Exception as e:
                        self.logger.warning("S2 search error for '%s': %s", topic, e)
                        break

                # Without API key, S2 has strict rate limits (~1 req/5 seconds)
                if idx < len(topics) - 1:
                    delay = 3.0 if api_key else 6.0
                    await asyncio.sleep(delay)

        self.logger.info("Semantic Scholar total: %d papers from %d topics", len(all_items), len(topics))
        return all_items[:max_results]

    async def _search_topic(
        self,
        client: httpx.AsyncClient,
        topic: str,
        limit: int,
        target_date: date,
    ) -> list[SourceItem]:
        """Search papers for a single topic."""
        # Look back 7 days to catch recent publications
        date_from = target_date - timedelta(days=7)

        params = {
            "query": topic,
            "limit": min(limit, 100),
            "fields": S2_FIELDS,
            "year": str(target_date.year),
            "fieldsOfStudy": "Computer Science",
        }

        resp = await client.get(S2_API, params=params)
        resp.raise_for_status()
        data = resp.json()

        results: list[SourceItem] = []
        for paper in data.get("data", []):
            pub_date_str = paper.get("publicationDate")
            if pub_date_str:
                try:
                    pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if pub_date.date() < date_from:
                        continue
                except ValueError:
                    pass

            paper_id = paper.get("paperId", "")
            if not paper_id:
                continue

            authors = [
                a.get("name", "") for a in paper.get("authors", [])
                if a.get("name")
            ]

            external_ids = paper.get("externalIds", {}) or {}
            arxiv_id = external_ids.get("ArXiv", "")
            doi = external_ids.get("DOI", "")

            url = paper.get("url", f"https://www.semanticscholar.org/paper/{paper_id}")

            pub_dt = datetime.now(tz=timezone.utc)
            if pub_date_str:
                try:
                    pub_dt = datetime.strptime(pub_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            results.append(SourceItem(
                id=f"s2:{paper_id}",
                source_type=SourceType.SEMANTIC_SCHOLAR,
                title=paper.get("title", ""),
                url=url,
                authors=authors[:10],
                published=pub_dt,
                content_snippet=(paper.get("abstract") or "")[:2000],
                metadata={
                    "paper_id": paper_id,
                    "citation_count": paper.get("citationCount", 0),
                    "year": paper.get("year"),
                    "arxiv_id": arxiv_id,
                    "doi": doi,
                    "source_name": "Semantic Scholar",
                },
            ))

        return results
