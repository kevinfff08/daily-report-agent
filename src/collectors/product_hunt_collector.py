"""Collector for Product Hunt via GraphQL API."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType

PH_API = "https://api.producthunt.com/v2/api/graphql"

POSTS_QUERY = """
query($postedAfter: DateTime!, $postedBefore: DateTime!, $topic: String, $first: Int!) {
  posts(
    postedAfter: $postedAfter,
    postedBefore: $postedBefore,
    topic: $topic,
    order: VOTES,
    first: $first
  ) {
    edges {
      node {
        id
        name
        tagline
        description
        url
        votesCount
        createdAt
        website
        topics {
          edges {
            node {
              name
            }
          }
        }
        makers {
          name
        }
      }
    }
  }
}
"""


class ProductHuntCollector(BaseCollector):
    """Collects top AI products from Product Hunt."""

    source_name = "product_hunt"

    async def collect(self, target_date: date) -> list[SourceItem]:
        token = os.environ.get("PRODUCT_HUNT_TOKEN", "")
        if not token:
            self.logger.warning("PRODUCT_HUNT_TOKEN not set, skipping Product Hunt collection")
            return []

        topics: list[str] = self.config.get("topics", ["artificial-intelligence"])
        max_items: int = self.config.get("max_items", 20)

        # Look back 2 days to ensure we catch products even on slow days
        from datetime import timedelta
        start_date = target_date - timedelta(days=2)
        posted_after = datetime(
            start_date.year, start_date.month, start_date.day,
            tzinfo=timezone.utc,
        ).isoformat()
        posted_before = datetime(
            target_date.year, target_date.month, target_date.day,
            23, 59, 59, tzinfo=timezone.utc,
        ).isoformat()

        all_items: list[SourceItem] = []
        seen_ids: set[str] = set()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            for topic in topics:
                try:
                    items = await self._fetch_topic(
                        client, topic, posted_after, posted_before, max_items,
                    )
                    for item in items:
                        if item.id not in seen_ids:
                            seen_ids.add(item.id)
                            all_items.append(item)
                except Exception as e:
                    self.logger.warning("Product Hunt error for topic '%s': %s", topic, e)

        all_items = all_items[:max_items]
        self.logger.info("Product Hunt total: %d products", len(all_items))
        return all_items

    async def _fetch_topic(
        self,
        client: httpx.AsyncClient,
        topic: str,
        posted_after: str,
        posted_before: str,
        max_items: int,
    ) -> list[SourceItem]:
        """Fetch products for a single topic."""
        variables = {
            "postedAfter": posted_after,
            "postedBefore": posted_before,
            "topic": topic,
            "first": max_items,
        }

        resp = await client.post(
            PH_API,
            json={"query": POSTS_QUERY, "variables": variables},
        )
        resp.raise_for_status()
        data = resp.json()

        edges = data.get("data", {}).get("posts", {}).get("edges", [])
        results: list[SourceItem] = []

        for edge in edges:
            node = edge.get("node", {})
            post_id = node.get("id", "")
            if not post_id:
                continue

            created_str = node.get("createdAt", "")
            try:
                published = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                published = datetime.now(tz=timezone.utc)

            # Extract topic names
            topic_names = [
                t.get("node", {}).get("name", "")
                for t in node.get("topics", {}).get("edges", [])
                if t.get("node", {}).get("name")
            ]

            # Extract maker names
            makers = [
                m.get("name", "") for m in node.get("makers", [])
                if m.get("name")
            ]

            results.append(SourceItem(
                id=f"ph:{post_id}",
                source_type=SourceType.PRODUCT_HUNT,
                title=node.get("name", ""),
                url=node.get("url", ""),
                authors=makers[:5],
                published=published,
                content_snippet=(
                    f"{node.get('tagline', '')}. {node.get('description', '')}"
                )[:1000],
                metadata={
                    "post_id": post_id,
                    "tagline": node.get("tagline", ""),
                    "votes_count": node.get("votesCount", 0),
                    "website": node.get("website", ""),
                    "topics": topic_names,
                    "source_name": "Product Hunt",
                },
            ))

        return results
