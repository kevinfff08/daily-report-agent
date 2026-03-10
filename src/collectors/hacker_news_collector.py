"""Collector for Hacker News via the Firebase API."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType


class HackerNewsCollector(BaseCollector):
    """Collects top stories from Hacker News."""

    source_name = "hackernews"

    HN_API = "https://hacker-news.firebaseio.com/v0"

    async def collect(self, target_date: date) -> list[SourceItem]:
        max_items = self.config.get("max_items", 30)
        min_score = self.config.get("min_score", 50)
        keywords = [kw.lower() for kw in self.config.get("keywords", [])]

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get top story IDs
            try:
                resp = await client.get(f"{self.HN_API}/topstories.json")
                resp.raise_for_status()
                story_ids = resp.json()[:max_items * 3]  # Fetch extra to filter
            except (httpx.HTTPError, ValueError) as e:
                self.logger.warning("HN API error fetching top stories: %s", e)
                return []

            # Fetch story details concurrently (in batches of 10)
            items: list[SourceItem] = []
            for batch_start in range(0, len(story_ids), 10):
                batch = story_ids[batch_start:batch_start + 10]
                tasks = [self._fetch_story(client, sid) for sid in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, SourceItem):
                        # Apply filters
                        score = result.metadata.get("score", 0)
                        if score < min_score:
                            continue
                        if keywords and not self._matches_keywords(result, keywords):
                            continue
                        items.append(result)

                        if len(items) >= max_items:
                            break

                if len(items) >= max_items:
                    break
                await asyncio.sleep(0.5)

        self.logger.info("HN total: %d stories (filtered from %d)", len(items), len(story_ids))
        return items

    async def _fetch_story(self, client: httpx.AsyncClient, story_id: int) -> SourceItem | None:
        """Fetch a single HN story."""
        try:
            resp = await client.get(f"{self.HN_API}/item/{story_id}.json")
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

        if not data or data.get("type") != "story":
            return None

        title = data.get("title", "")
        url = data.get("url", f"https://news.ycombinator.com/item?id={story_id}")
        by = data.get("by", "")
        score = data.get("score", 0)
        descendants = data.get("descendants", 0)
        time_val = data.get("time", 0)
        text = data.get("text", "")  # For Ask HN / Show HN

        published = datetime.fromtimestamp(time_val, tz=timezone.utc) if time_val else datetime.now(tz=timezone.utc)

        return SourceItem(
            id=f"hn:{story_id}",
            source_type=SourceType.HACKER_NEWS,
            title=title,
            url=url,
            authors=[by] if by else [],
            published=published,
            content_snippet=text[:500] if text else "",
            metadata={
                "story_id": story_id,
                "score": score,
                "num_comments": descendants,
                "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
                "source_name": "Hacker News",
            },
        )

    @staticmethod
    def _matches_keywords(item: SourceItem, keywords: list[str]) -> bool:
        """Check if item matches any keyword."""
        text = f"{item.title} {item.content_snippet}".lower()
        return any(kw in text for kw in keywords)
