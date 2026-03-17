"""Collector for GitHub Trending repositories via HTML scraping."""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timezone

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType

GITHUB_TRENDING_URL = "https://github.com/trending"


class GitHubTrendingCollector(BaseCollector):
    """Collects trending repositories from GitHub."""

    source_name = "github_trending"

    async def collect(self, target_date: date) -> list[SourceItem]:
        languages: list[str] = self.config.get("languages", ["python", ""])
        since: str = self.config.get("since", "daily")
        max_items: int = self.config.get("max_items", 30)

        all_items: list[SourceItem] = []
        seen_ids: set[str] = set()

        import os
        token = os.environ.get("GITHUB_TOKEN", "")
        headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (compatible; DailyReport/1.0)",
        }
        if token:
            headers["Authorization"] = f"token {token}"

        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            for lang in languages:
                try:
                    items = await self._fetch_trending(client, lang, since, target_date)
                    for item in items:
                        if item.id not in seen_ids:
                            seen_ids.add(item.id)
                            all_items.append(item)
                except Exception as e:
                    self.logger.warning("Error fetching GitHub trending for '%s': %s", lang, e)

                await asyncio.sleep(0.5)

        # Limit total
        all_items = all_items[:max_items]
        self.logger.info("GitHub Trending total: %d repos", len(all_items))
        return all_items

    async def _fetch_trending(
        self,
        client: httpx.AsyncClient,
        language: str,
        since: str,
        target_date: date,
    ) -> list[SourceItem]:
        """Fetch trending repos for a specific language."""
        url = GITHUB_TRENDING_URL
        if language:
            url = f"{url}/{language}"

        resp = await client.get(url, params={"since": since})
        resp.raise_for_status()
        html = resp.text

        return self._parse_trending_html(html, target_date)

    def _parse_trending_html(self, html: str, target_date: date) -> list[SourceItem]:
        """Parse GitHub trending page HTML to extract repository info."""
        results: list[SourceItem] = []

        # Each repo is in an <article class="Box-row"> element
        articles = re.split(r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>', html)
        if len(articles) <= 1:
            # Try alternative pattern
            articles = re.split(r'<article\s', html)

        for article in articles[1:]:  # Skip content before first article
            repo = self._parse_article(article, target_date)
            if repo:
                results.append(repo)

        return results

    def _parse_article(self, article_html: str, target_date: date) -> SourceItem | None:
        """Parse a single trending article HTML block."""
        # Extract repo path: /owner/repo in an <a> href
        repo_match = re.search(r'href="(/[^/]+/[^/"]+)"', article_html)
        if not repo_match:
            return None

        repo_path = repo_match.group(1).strip("/")
        parts = repo_path.split("/")
        if len(parts) != 2:
            return None

        owner, repo_name = parts

        # Extract description
        desc_match = re.search(r'<p[^>]*>([^<]+)</p>', article_html)
        description = desc_match.group(1).strip() if desc_match else ""

        # Extract total stars
        stars_match = re.search(
            r'href="/' + re.escape(repo_path) + r'/stargazers"[^>]*>\s*([0-9,]+)\s*</a>',
            article_html,
        )
        if not stars_match:
            # Alternative: look for octicon-star followed by a number
            stars_match = re.search(r'octicon-star[^>]*>.*?</svg>\s*([0-9,]+)', article_html)
        total_stars = int(stars_match.group(1).replace(",", "")) if stars_match else 0

        # Extract language
        lang_match = re.search(r'itemprop="programmingLanguage">([^<]+)</span>', article_html)
        language = lang_match.group(1).strip() if lang_match else ""

        # Extract stars today
        today_match = re.search(r'([0-9,]+)\s+stars\s+today', article_html)
        stars_today = int(today_match.group(1).replace(",", "")) if today_match else 0

        return SourceItem(
            id=f"github:{repo_path}",
            source_type=SourceType.GITHUB_TRENDING,
            title=f"{owner}/{repo_name}",
            url=f"https://github.com/{repo_path}",
            authors=[owner],
            published=datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc),
            content_snippet=description[:500],
            metadata={
                "repo_name": repo_name,
                "owner": owner,
                "stars": total_stars,
                "language": language,
                "stars_today": stars_today,
                "source_name": "GitHub Trending",
            },
        )
