"""Collector for arXiv papers via the arXiv API."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from urllib.parse import quote

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType


class ArxivCollector(BaseCollector):
    """Collects papers from arXiv using the Atom API."""

    source_name = "arxiv"

    ARXIV_API = "https://export.arxiv.org/api/query"

    async def collect(self, target_date: date) -> list[SourceItem]:
        categories = self.config.get("categories", ["cs.AI", "cs.CL", "cs.CV", "cs.LG"])
        max_per_cat = self.config.get("max_results_per_category", 50)

        all_items: list[SourceItem] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=60.0) as client:
            for cat in categories:
                items = await self._fetch_category(client, cat, max_per_cat, target_date)
                for item in items:
                    if item.id not in seen_ids:
                        seen_ids.add(item.id)
                        all_items.append(item)
                # Be polite to the arXiv API
                await asyncio.sleep(3.0)

        self.logger.info("arXiv total: %d unique papers across %d categories", len(all_items), len(categories))
        return all_items

    async def _fetch_category(
        self, client: httpx.AsyncClient, category: str, max_results: int, target_date: date
    ) -> list[SourceItem]:
        """Fetch papers for a single arXiv category."""
        # Search for papers submitted in the last 2 days to catch timezone differences
        date_from = target_date - timedelta(days=2)
        query = f"cat:{category}"

        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            resp = await client.get(self.ARXIV_API, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            self.logger.warning("arXiv API error for %s: %s", category, e)
            return []

        return self._parse_atom_response(resp.text, category, date_from)

    def _parse_atom_response(self, xml_text: str, category: str, date_from: date) -> list[SourceItem]:
        """Parse arXiv Atom XML response into SourceItems."""
        import xml.etree.ElementTree as ET

        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        items: list[SourceItem] = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            self.logger.warning("Failed to parse arXiv XML: %s", e)
            return []

        for entry in root.findall("atom:entry", ns):
            try:
                arxiv_id_el = entry.find("atom:id", ns)
                if arxiv_id_el is None or arxiv_id_el.text is None:
                    continue
                arxiv_id = arxiv_id_el.text.split("/abs/")[-1]

                title_el = entry.find("atom:title", ns)
                title = " ".join((title_el.text or "").split()) if title_el is not None else ""

                summary_el = entry.find("atom:summary", ns)
                summary = " ".join((summary_el.text or "").split()) if summary_el is not None else ""

                published_el = entry.find("atom:published", ns)
                if published_el is not None and published_el.text:
                    published = datetime.fromisoformat(published_el.text.replace("Z", "+00:00"))
                    if published.date() < date_from:
                        continue
                else:
                    published = datetime.now()

                authors = []
                for author_el in entry.findall("atom:author", ns):
                    name_el = author_el.find("atom:name", ns)
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text)

                categories = []
                for cat_el in entry.findall("atom:category", ns):
                    term = cat_el.get("term", "")
                    if term:
                        categories.append(term)

                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
                abs_url = f"https://arxiv.org/abs/{arxiv_id}"

                items.append(SourceItem(
                    id=f"arxiv:{arxiv_id}",
                    source_type=SourceType.ARXIV_PAPER,
                    title=title,
                    url=abs_url,
                    authors=authors,
                    published=published,
                    content_snippet=summary,
                    metadata={
                        "arxiv_id": arxiv_id,
                        "categories": categories,
                        "primary_category": category,
                        "pdf_url": pdf_url,
                        "source_name": f"arXiv {category}",
                    },
                ))
            except Exception as e:
                self.logger.debug("Skipping arXiv entry: %s", e)
                continue

        return items
