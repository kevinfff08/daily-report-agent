"""Collector for Bilibili videos via public API with WBI signing."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from datetime import date, datetime, timezone
from functools import lru_cache
from urllib.parse import urlencode

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType

# WBI mixin key index table (fixed constant, used to rearrange raw key)
_WBI_MIXIN_KEY_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
SEARCH_URL = "https://api.bilibili.com/x/space/wbi/arc/search"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}


def _get_mixin_key(raw_key: str) -> str:
    """Apply mixin table to raw WBI key, return first 32 chars."""
    return "".join(raw_key[i] for i in _WBI_MIXIN_KEY_TABLE if i < len(raw_key))[:32]


def _sign_params(params: dict, mixin_key: str) -> dict:
    """Add WBI signature (w_rid) to params."""
    params = {**params, "wts": int(time.time())}
    # Sort by key, filter out problematic chars
    sorted_params = dict(sorted(params.items()))
    query = urlencode(sorted_params)
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return {**sorted_params, "w_rid": w_rid}


class BilibiliCollector(BaseCollector):
    """Collects latest videos from configured Bilibili UP主."""

    source_name = "bilibili"

    def __init__(self, store: "LocalStore", config: dict | None = None):
        super().__init__(store, config)
        self._mixin_key: str | None = None

    async def collect(self, target_date: date) -> list[SourceItem]:
        users: list[dict] = self.config.get("users", [])
        max_per_user: int = self.config.get("max_results_per_user", 5)

        if not users:
            self.logger.info("No Bilibili users configured")
            return []

        all_items: list[SourceItem] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
            # Fetch WBI key
            mixin_key = await self._get_wbi_key(client)
            if not mixin_key:
                self.logger.warning("Failed to get Bilibili WBI key, skipping")
                return []

            for user in users:
                user_name = user.get("name", "Unknown")
                uid = user.get("uid", 0)
                if not uid:
                    continue

                try:
                    items = await self._fetch_user_videos(
                        client, uid, user_name, max_per_user, mixin_key, target_date,
                    )
                    for item in items:
                        if item.id not in seen_ids:
                            seen_ids.add(item.id)
                            all_items.append(item)
                except Exception as e:
                    self.logger.warning("Error fetching Bilibili user %s: %s", user_name, e)

                await asyncio.sleep(0.5)

        self.logger.info("Bilibili total: %d videos from %d users", len(all_items), len(users))
        return all_items

    async def _get_wbi_key(self, client: httpx.AsyncClient) -> str | None:
        """Fetch and compute WBI mixin key from nav API."""
        if self._mixin_key:
            return self._mixin_key

        try:
            resp = await client.get(NAV_URL)
            resp.raise_for_status()
            data = resp.json()
            wbi_img = data.get("data", {}).get("wbi_img", {})
            img_url = wbi_img.get("img_url", "")
            sub_url = wbi_img.get("sub_url", "")

            # Extract key from URL: take filename stem (before .png)
            img_key = img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
            sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""
            raw_key = img_key + sub_key

            if not raw_key:
                return None

            self._mixin_key = _get_mixin_key(raw_key)
            return self._mixin_key
        except Exception as e:
            self.logger.warning("Failed to fetch WBI key: %s", e)
            return None

    async def _fetch_user_videos(
        self,
        client: httpx.AsyncClient,
        uid: int,
        user_name: str,
        max_results: int,
        mixin_key: str,
        target_date: date,
    ) -> list[SourceItem]:
        """Fetch recent videos from a single Bilibili user."""
        params = {
            "mid": uid,
            "ps": max_results,
            "pn": 1,
            "order": "pubdate",
        }
        signed_params = _sign_params(params, mixin_key)

        resp = await client.get(SEARCH_URL, params=signed_params)
        resp.raise_for_status()
        data = resp.json()

        vlist = data.get("data", {}).get("list", {}).get("vlist", [])
        if not vlist:
            return []

        # Filter by date: keep videos from the last 7 days
        # (many UP主 don't post daily, so a wider window is more useful)
        cutoff_ts = datetime(
            target_date.year, target_date.month, target_date.day,
            tzinfo=timezone.utc,
        ).timestamp() - 86400 * 7  # 7 days before

        results: list[SourceItem] = []
        for v in vlist:
            created = v.get("created", 0)
            if created < cutoff_ts:
                continue

            bvid = v.get("bvid", "")
            published = datetime.fromtimestamp(created, tz=timezone.utc)

            results.append(SourceItem(
                id=f"bilibili:{bvid}",
                source_type=SourceType.BILIBILI_VIDEO,
                title=v.get("title", ""),
                url=f"https://www.bilibili.com/video/{bvid}",
                authors=[user_name],
                published=published,
                content_snippet=v.get("description", "")[:1000],
                metadata={
                    "bvid": bvid,
                    "aid": v.get("aid", 0),
                    "uid": uid,
                    "up_name": user_name,
                    "play_count": v.get("play", 0),
                    "comment_count": v.get("comment", 0),
                    "source_name": user_name,
                },
            ))

        return results
