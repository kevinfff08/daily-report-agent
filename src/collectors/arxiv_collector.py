"""Collector for arXiv papers via the arXiv API."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import NamedTuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import re

import httpx

from src.collectors.base import BaseCollector
from src.models.source import SourceItem, SourceType

_CATEGORY_DELAY_SECONDS = 5.0
_RATE_LIMIT_COOLDOWN_SECONDS = 45.0
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 15.0
_MIN_MAX_RESULTS = 5
_RSS_FALLBACK_LIMIT = 30
_CLIENT_TIMEOUT_SECONDS = 60.0
_PRIMARY_LOOKBACK_DAYS = 2
_EXPANDED_LOOKBACK_DAYS = 4
_REQUEST_HEADERS = {
    "User-Agent": "DailyReport/1.0 (research digest collector)",
    "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
}
_RSS_TITLE_RE = re.compile(r"^(?P<title>.+?)\s+\(arXiv:(?P<arxiv_id>[^\s\)]+).*$")
_CATEGORY_SUFFIX_RE = re.compile(r"\s+\[[^\]]+\](?:\s+UPDATED)?$")


class _FetchCategoryResult(NamedTuple):
    items: list[SourceItem]
    rate_limited: bool


class ArxivCollector(BaseCollector):
    """Collects papers from arXiv using the Atom API."""

    source_name = "arxiv"

    ARXIV_API = "https://export.arxiv.org/api/query"
    ARXIV_RSS = "https://export.arxiv.org/rss/{category}"

    async def collect(self, target_date: date) -> list[SourceItem]:
        categories = self.config.get("categories", ["cs.AI", "cs.CL", "cs.CV", "cs.LG"])
        max_per_cat = self.config.get("max_results_per_category", 50)

        all_items: list[SourceItem] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(
            timeout=_CLIENT_TIMEOUT_SECONDS,
            headers=_REQUEST_HEADERS,
            trust_env=False,
        ) as client:
            for cat in categories:
                self.logger.info(
                    "arXiv category %s: starting API fetch (max_results=%d, target_date=%s)",
                    cat,
                    max_per_cat,
                    target_date.isoformat(),
                )
                result = await self._fetch_category(client, cat, max_per_cat, target_date)
                items = result.items
                if not items:
                    self.logger.info(
                        "arXiv category %s: API returned no usable items, trying RSS fallback",
                        cat,
                    )
                    rss_items = await self._fetch_category_rss(client, cat, target_date)
                    if rss_items:
                        self.logger.info(
                            "arXiv RSS fallback recovered %d items for %s",
                            len(rss_items),
                            cat,
                        )
                        items = rss_items
                    else:
                        self.logger.info("arXiv category %s: RSS fallback returned 0 items", cat)
                for item in items:
                    if item.id not in seen_ids:
                        seen_ids.add(item.id)
                        all_items.append(item)
                self.logger.info(
                    "arXiv category %s: kept %d items (%d cumulative unique)",
                    cat,
                    len(items),
                    len(all_items),
                )
                await asyncio.sleep(_CATEGORY_DELAY_SECONDS)
                if result.rate_limited:
                    self.logger.info(
                        "arXiv rate limit detected for %s, cooling down %.0fs before next category",
                        cat,
                        _RATE_LIMIT_COOLDOWN_SECONDS,
                    )
                    await asyncio.sleep(_RATE_LIMIT_COOLDOWN_SECONDS)

        self.logger.info("arXiv total: %d unique papers across %d categories", len(all_items), len(categories))
        return all_items

    async def _fetch_category(
        self, client: httpx.AsyncClient, category: str, max_results: int, target_date: date
    ) -> _FetchCategoryResult:
        """Fetch papers for a single arXiv category."""
        query = f"cat:{category}"

        last_error: httpx.HTTPError | None = None
        rate_limited = False
        requested_results = max_results

        for attempt in range(_MAX_RETRIES):
            params = {
                "search_query": query,
                "start": 0,
                "max_results": requested_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            try:
                self.logger.debug(
                    "arXiv category %s: API request attempt %d/%d with params=%s",
                    category,
                    attempt + 1,
                    _MAX_RETRIES,
                    params,
                )
                resp = await client.get(self.ARXIV_API, params=params)
                self.logger.info(
                    "arXiv category %s: API response status=%d on attempt %d/%d",
                    category,
                    resp.status_code,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                resp.raise_for_status()
                effective_target_date = self._effective_target_date(resp, target_date, category, source="api")
                items, date_from = self._parse_atom_response_with_lookback(
                    resp.text,
                    category,
                    effective_target_date,
                )
                self.logger.info(
                    "arXiv category %s: parsed %d API items using date window %s..%s",
                    category,
                    len(items),
                    date_from.isoformat(),
                    effective_target_date.isoformat(),
                )
                return _FetchCategoryResult(
                    items=items,
                    rate_limited=rate_limited,
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                if status_code not in _RETRY_STATUS_CODES:
                    self.logger.warning(
                        "arXiv API error for %s: %s (%r)",
                        category,
                        type(exc).__name__,
                        exc,
                    )
                    return _FetchCategoryResult(items=[], rate_limited=rate_limited)

                delay = self._retry_delay_seconds(exc.response, attempt)
                if status_code == 429:
                    rate_limited = True
                    next_results = self._reduced_max_results(requested_results)
                    self.logger.info(
                        "arXiv rate limited for %s, retrying in %.0fs with max_results=%d (attempt %d/%d)",
                        category,
                        delay,
                        requested_results,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    if next_results < requested_results:
                        self.logger.info(
                            "arXiv reducing request size for %s from %d to %d after rate limit",
                            category,
                            requested_results,
                            next_results,
                        )
                        requested_results = next_results
                else:
                    self.logger.warning(
                        "arXiv transient error for %s (%d), retrying in %.0fs (attempt %d/%d)",
                        category,
                        status_code,
                        delay,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                await asyncio.sleep(delay)
            except httpx.HTTPError as exc:
                last_error = exc
                self.logger.warning(
                    "arXiv API error for %s: %s (%r)",
                    category,
                    type(exc).__name__,
                    exc,
                )
                return _FetchCategoryResult(items=[], rate_limited=rate_limited)

        self.logger.warning(
            "arXiv API error for %s after retries: %s (%r)",
            category,
            type(last_error).__name__ if last_error is not None else "UnknownError",
            last_error,
        )
        return _FetchCategoryResult(items=[], rate_limited=rate_limited)

    def _retry_delay_seconds(self, response: httpx.Response, attempt: int) -> float:
        """Compute retry delay, respecting Retry-After when present."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                pass
        return _BACKOFF_BASE_SECONDS * (2 ** attempt)

    @staticmethod
    def _reduced_max_results(current: int) -> int:
        """Reduce request size after rate limiting while keeping useful coverage."""
        if current <= _MIN_MAX_RESULTS:
            return current
        if current <= 10:
            return _MIN_MAX_RESULTS
        return max(current // 2, _MIN_MAX_RESULTS)

    async def _fetch_category_rss(
        self,
        client: httpx.AsyncClient,
        category: str,
        target_date: date,
    ) -> list[SourceItem]:
        """Fallback to arXiv RSS when the Atom API returns no usable results."""
        try:
            rss_url = self._rss_url(category)
            self.logger.debug("arXiv category %s: RSS fallback request url=%s", category, rss_url)
            resp = await client.get(rss_url)
            self.logger.info(
                "arXiv category %s: RSS fallback response status=%d",
                category,
                resp.status_code,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self.logger.warning(
                "arXiv RSS fallback error for %s: %s (%r)",
                category,
                type(exc).__name__,
                exc,
            )
            return []

        effective_target_date = self._effective_target_date(resp, target_date, category, source="rss")
        items, date_from = self._parse_rss_response_with_lookback(
            resp.text,
            category,
            effective_target_date,
        )
        items = items[:_RSS_FALLBACK_LIMIT]
        self.logger.info(
            "arXiv category %s: parsed %d RSS items using date window %s..%s",
            category,
            len(items),
            date_from.isoformat(),
            effective_target_date.isoformat(),
        )
        return items

    def _parse_atom_response_with_lookback(
        self,
        xml_text: str,
        category: str,
        effective_target_date: date,
    ) -> tuple[list[SourceItem], date]:
        """Parse Atom response and widen the lookback window when arXiv feed lags a few days."""
        primary_date_from = effective_target_date - timedelta(days=_PRIMARY_LOOKBACK_DAYS)
        items = self._parse_atom_response(xml_text, category, primary_date_from)
        if items:
            return items, primary_date_from

        expanded_date_from = effective_target_date - timedelta(days=_EXPANDED_LOOKBACK_DAYS)
        if expanded_date_from == primary_date_from:
            return items, primary_date_from

        expanded_items = self._parse_atom_response(xml_text, category, expanded_date_from)
        if expanded_items:
            self.logger.info(
                "arXiv category %s: widened API lookback window from %d to %d days and recovered %d items",
                category,
                _PRIMARY_LOOKBACK_DAYS,
                _EXPANDED_LOOKBACK_DAYS,
                len(expanded_items),
            )
            return expanded_items, expanded_date_from
        return items, primary_date_from

    def _parse_rss_response_with_lookback(
        self,
        xml_text: str,
        category: str,
        effective_target_date: date,
    ) -> tuple[list[SourceItem], date]:
        """Parse RSS response and widen the lookback window when needed."""
        primary_date_from = effective_target_date - timedelta(days=_PRIMARY_LOOKBACK_DAYS)
        items = self._parse_rss_response(xml_text, category, primary_date_from)
        if items:
            return items, primary_date_from

        expanded_date_from = effective_target_date - timedelta(days=_EXPANDED_LOOKBACK_DAYS)
        if expanded_date_from == primary_date_from:
            return items, primary_date_from

        expanded_items = self._parse_rss_response(xml_text, category, expanded_date_from)
        if expanded_items:
            self.logger.info(
                "arXiv category %s: widened RSS lookback window from %d to %d days and recovered %d items",
                category,
                _PRIMARY_LOOKBACK_DAYS,
                _EXPANDED_LOOKBACK_DAYS,
                len(expanded_items),
            )
            return expanded_items, expanded_date_from
        return items, primary_date_from

    @classmethod
    def _rss_url(cls, category: str) -> str:
        base = cls.ARXIV_RSS.format(category=category)
        parts = list(urlparse(base))
        query = dict(parse_qsl(parts[4], keep_blank_values=True))
        query["version"] = "2.0"
        parts[4] = urlencode(query)
        return urlunparse(parts)

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

    def _parse_rss_response(self, xml_text: str, category: str, date_from: date) -> list[SourceItem]:
        """Parse arXiv RSS XML into SourceItems."""
        import xml.etree.ElementTree as ET

        ns = {
            "rss": "http://purl.org/rss/1.0/",
            "dc": "http://purl.org/dc/elements/1.1/",
        }
        items: list[SourceItem] = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            self.logger.warning("Failed to parse arXiv RSS XML: %s", exc)
            return []

        stripper = _HTMLStripper()
        for entry in root.findall("rss:item", ns):
            try:
                title_text = (entry.findtext("rss:title", default="", namespaces=ns) or "").strip()
                title_match = _RSS_TITLE_RE.match(title_text)
                if not title_match:
                    continue

                arxiv_id = title_match.group("arxiv_id").strip()
                title = _CATEGORY_SUFFIX_RE.sub("", title_match.group("title").strip())
                link = (entry.findtext("rss:link", default="", namespaces=ns) or "").strip()
                if not link:
                    link = f"https://arxiv.org/abs/{arxiv_id}"

                description_html = entry.findtext("rss:description", default="", namespaces=ns) or ""
                summary = stripper.extract(description_html)

                creator_html = entry.findtext("dc:creator", default="", namespaces=ns) or ""
                creator_text = stripper.extract(creator_html)
                authors = [author.strip() for author in creator_text.split(",") if author.strip()]

                date_text = (entry.findtext("dc:date", default="", namespaces=ns) or "").strip()
                if not date_text:
                    date_text = (entry.findtext("rss:pubDate", default="", namespaces=ns) or "").strip()
                if date_text:
                    published = parsedate_to_datetime(date_text)
                else:
                    published = datetime.now()
                if published.date() < date_from:
                    continue

                items.append(
                    SourceItem(
                        id=f"arxiv:{arxiv_id}",
                        source_type=SourceType.ARXIV_PAPER,
                        title=title,
                        url=link,
                        authors=authors,
                        published=published,
                        content_snippet=summary,
                        metadata={
                            "arxiv_id": arxiv_id,
                            "categories": [category],
                            "primary_category": category,
                            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                            "source_name": f"arXiv {category}",
                            "ingest_source": "rss_fallback",
                        },
                    )
                )
            except Exception as exc:
                self.logger.debug("Skipping arXiv RSS entry: %s", exc)
                continue

        return items

    def _effective_target_date(
        self,
        response: httpx.Response,
        target_date: date,
        category: str,
        *,
        source: str,
    ) -> date:
        """Clamp future-looking target dates using the server's current date header."""
        date_header = response.headers.get("Date", "")
        if not date_header:
            return target_date

        try:
            server_date = parsedate_to_datetime(date_header).date()
        except Exception:
            return target_date

        if target_date > server_date:
            self.logger.info(
                "arXiv %s response date for %s is %s, clamping target date from %s",
                source,
                category,
                server_date.isoformat(),
                target_date.isoformat(),
            )
            return server_date
        return target_date


class _HTMLStripper(HTMLParser):
    """Strip HTML tags from RSS title/description/creator fields."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self._parts.append(text)

    def extract(self, html_text: str) -> str:
        self._parts = []
        self.feed(unescape(html_text))
        return " ".join(self._parts).strip()
