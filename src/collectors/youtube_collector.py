"""Collector for YouTube videos via Data API v3."""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


class YouTubeCollector(BaseCollector):
    """Collects latest videos from configured YouTube channels."""

    source_name = "youtube"

    async def collect(self, target_date: date) -> list[SourceItem]:
        api_key = os.environ.get("YOUTUBE_API_KEY", "")
        if not api_key:
            self.logger.warning("YOUTUBE_API_KEY not set, skipping YouTube collection")
            return []

        channels: list[dict] = self.config.get("channels", [])
        max_per_channel: int = self.config.get("max_results_per_channel", 5)

        if not channels:
            self.logger.info("No YouTube channels configured")
            return []

        if len(channels) > 20:
            self.logger.warning(
                "Many channels configured (%d). YouTube quota is 10,000 units/day, "
                "each search costs 100 units.",
                len(channels),
            )

        # publishedAfter: start of target_date - 1 day (UTC)
        published_after = datetime(
            target_date.year, target_date.month, target_date.day,
            tzinfo=timezone.utc,
        ) - timedelta(days=1)

        all_items: list[SourceItem] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for ch in channels:
                ch_name = ch.get("name", "Unknown")
                ch_id = ch.get("channel_id", "")
                if not ch_id:
                    continue

                try:
                    items = await self._fetch_channel_videos(
                        client, api_key, ch_id, ch_name,
                        max_per_channel, published_after,
                    )
                    for item in items:
                        if item.id not in seen_ids:
                            seen_ids.add(item.id)
                            all_items.append(item)
                except Exception as e:
                    self.logger.warning("Error fetching channel %s: %s", ch_name, e)

                await asyncio.sleep(0.2)

        self.logger.info("YouTube total: %d videos from %d channels", len(all_items), len(channels))
        return all_items

    async def _fetch_channel_videos(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        channel_id: str,
        channel_name: str,
        max_results: int,
        published_after: datetime,
    ) -> list[SourceItem]:
        """Fetch recent videos from a single channel."""
        params = {
            "key": api_key,
            "channelId": channel_id,
            "part": "snippet",
            "order": "date",
            "type": "video",
            "maxResults": max_results,
            "publishedAfter": published_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        resp = await client.get(f"{YOUTUBE_API}/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        video_ids = []
        snippets: dict[str, dict] = {}
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                video_ids.append(vid)
                snippets[vid] = item.get("snippet", {})

        if not video_ids:
            return []

        # Fetch video statistics
        stats = await self._fetch_video_stats(client, api_key, video_ids)

        results: list[SourceItem] = []
        for vid in video_ids:
            snip = snippets.get(vid, {})
            video_stats = stats.get(vid, {})

            published_str = snip.get("publishedAt", "")
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                published = datetime.now(tz=timezone.utc)

            results.append(SourceItem(
                id=f"youtube:{vid}",
                source_type=SourceType.YOUTUBE_VIDEO,
                title=snip.get("title", ""),
                url=f"https://www.youtube.com/watch?v={vid}",
                authors=[snip.get("channelTitle", channel_name)],
                published=published,
                content_snippet=snip.get("description", "")[:1000],
                metadata={
                    "video_id": vid,
                    "channel_name": channel_name,
                    "channel_id": channel_id,
                    "view_count": int(video_stats.get("viewCount", 0)),
                    "like_count": int(video_stats.get("likeCount", 0)),
                    "duration": video_stats.get("duration", ""),
                    "source_name": channel_name,
                },
            ))

        return results

    async def _fetch_video_stats(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        video_ids: list[str],
    ) -> dict[str, dict]:
        """Batch-fetch video statistics."""
        try:
            params = {
                "key": api_key,
                "id": ",".join(video_ids),
                "part": "statistics,contentDetails",
            }
            resp = await client.get(f"{YOUTUBE_API}/videos", params=params)
            resp.raise_for_status()
            data = resp.json()

            result = {}
            for item in data.get("items", []):
                vid = item.get("id", "")
                stats = item.get("statistics", {})
                details = item.get("contentDetails", {})
                result[vid] = {**stats, "duration": details.get("duration", "")}
            return result
        except Exception as e:
            self.logger.debug("Failed to fetch video stats: %s", e)
            return {}
