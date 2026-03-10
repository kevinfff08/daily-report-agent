"""Collector for RSS/Atom feeds (company blogs, news sites, academic blogs)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from time import mktime

import feedparser
import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType


class RSSCollector(BaseCollector):
    """Collects articles from configured RSS/Atom feeds."""

    source_name = "rss"

    async def collect(self, target_date: date) -> list[SourceItem]:
        feeds = self.config.get("feeds", [])
        if not feeds:
            self.logger.warning("No RSS feeds configured")
            return []

        all_items: list[SourceItem] = []
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for feed_cfg in feeds:
                items = await self._fetch_feed(client, feed_cfg, target_date)
                all_items.extend(items)
                await asyncio.sleep(1.0)

        self.logger.info("RSS total: %d articles from %d feeds", len(all_items), len(feeds))
        return all_items

    async def _fetch_feed(
        self, client: httpx.AsyncClient, feed_cfg: dict, target_date: date
    ) -> list[SourceItem]:
        """Fetch and parse a single RSS feed."""
        name = feed_cfg.get("name", "Unknown")
        url = feed_cfg.get("url", "")
        category = feed_cfg.get("category", "news")

        if not url:
            return []

        try:
            resp = await client.get(url, headers={"User-Agent": "DailyReport/0.1 (Research Tool)"})
            resp.raise_for_status()
            content = resp.text
        except httpx.HTTPError as e:
            self.logger.warning("RSS fetch failed for %s (%s): %s", name, url, e)
            return []

        feed = feedparser.parse(content)
        items: list[SourceItem] = []

        for entry in feed.entries:
            try:
                published = self._parse_entry_date(entry)
                # Keep items from the last 3 days to catch timezone differences
                if published and (target_date - published.date()).days > 3:
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = entry.get("summary", entry.get("description", ""))
                # Strip HTML tags from summary
                if summary:
                    import re
                    summary = re.sub(r"<[^>]+>", "", summary).strip()
                    summary = summary[:1000]

                authors = []
                if hasattr(entry, "authors"):
                    authors = [a.get("name", "") for a in entry.authors if a.get("name")]
                elif hasattr(entry, "author"):
                    authors = [entry.author]

                entry_id = entry.get("id", link) or link

                items.append(SourceItem(
                    id=f"rss:{name}:{hash(entry_id) % 10**8}",
                    source_type=SourceType.RSS_ARTICLE,
                    title=title,
                    url=link,
                    authors=authors,
                    published=published or datetime.now(tz=timezone.utc),
                    content_snippet=summary,
                    metadata={
                        "feed_name": name,
                        "feed_url": url,
                        "category": category,
                        "source_name": name,
                    },
                ))
            except Exception as e:
                self.logger.debug("Skipping RSS entry from %s: %s", name, e)
                continue

        return items

    @staticmethod
    def _parse_entry_date(entry) -> datetime | None:
        """Parse date from an RSS entry."""
        for attr in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                try:
                    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
                except (OverflowError, ValueError, OSError):
                    continue
        return None
