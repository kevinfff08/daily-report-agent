"""Collector for Reddit posts via the JSON API (no authentication required)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType


class RedditCollector(BaseCollector):
    """Collects hot posts from configured subreddits."""

    source_name = "reddit"

    REDDIT_BASE = "https://www.reddit.com"

    async def collect(self, target_date: date) -> list[SourceItem]:
        subreddits = self.config.get("subreddits", ["MachineLearning", "LocalLLaMA"])
        sort = self.config.get("sort", "hot")
        limit = self.config.get("limit", 25)

        all_items: list[SourceItem] = []
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "DailyReport/0.1 (Research Tool; contact: research@example.com)"},
        ) as client:
            for sub in subreddits:
                items = await self._fetch_subreddit(client, sub, sort, limit, target_date)
                all_items.extend(items)
                await asyncio.sleep(2.0)

        self.logger.info("Reddit total: %d posts from %d subreddits", len(all_items), len(subreddits))
        return all_items

    async def _fetch_subreddit(
        self, client: httpx.AsyncClient, subreddit: str, sort: str, limit: int, target_date: date
    ) -> list[SourceItem]:
        """Fetch posts from a single subreddit."""
        url = f"{self.REDDIT_BASE}/r/{subreddit}/{sort}.json"
        params = {"limit": limit, "t": "day"}

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            self.logger.warning("Reddit fetch failed for r/%s: %s", subreddit, e)
            return []

        items: list[SourceItem] = []
        children = data.get("data", {}).get("children", [])

        for child in children:
            try:
                post = child.get("data", {})
                created_utc = post.get("created_utc", 0)
                published = datetime.fromtimestamp(created_utc, tz=timezone.utc)

                # Only keep recent posts
                if (target_date - published.date()).days > 2:
                    continue

                title = post.get("title", "").strip()
                selftext = post.get("selftext", "")[:1000]
                post_id = post.get("id", "")
                permalink = post.get("permalink", "")
                post_url = post.get("url", "")
                score = post.get("score", 0)
                num_comments = post.get("num_comments", 0)
                author = post.get("author", "")

                items.append(SourceItem(
                    id=f"reddit:{subreddit}:{post_id}",
                    source_type=SourceType.REDDIT_POST,
                    title=title,
                    url=f"{self.REDDIT_BASE}{permalink}" if permalink else post_url,
                    authors=[author] if author else [],
                    published=published,
                    content_snippet=selftext,
                    metadata={
                        "subreddit": subreddit,
                        "score": score,
                        "num_comments": num_comments,
                        "post_url": post_url,
                        "source_name": f"r/{subreddit}",
                    },
                ))
            except Exception as e:
                self.logger.debug("Skipping Reddit post from r/%s: %s", subreddit, e)
                continue

        return items
