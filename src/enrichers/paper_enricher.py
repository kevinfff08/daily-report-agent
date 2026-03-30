"""Paper enricher: downloads arXiv PDFs and extracts full text."""

from __future__ import annotations

import tempfile
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import httpx

from src.logging_config import get_logger
from src.models.source import SourceItem

logger = get_logger("enrichers.paper")

# Max characters to extract from PDF (~8000 words, covers most papers)
_MAX_PDF_CHARS = 40_000


class PaperEnricher:
    """Enriches paper items by downloading and extracting full PDF text."""

    async def enrich(self, item: SourceItem) -> str:
        """Download paper PDF and extract text.

        Returns full text string, or empty string on failure.
        """
        pdf_url = self._get_pdf_url(item)
        if pdf_url:
            pdf_text = await self._extract_pdf_text(item, pdf_url)
            if pdf_text:
                return pdf_text

        fallback_text = await self._extract_fallback_text(item)
        if fallback_text:
            logger.info(
                "Extracted %d chars from fallback paper source: %s",
                len(fallback_text),
                item.title,
            )
            return fallback_text[:_MAX_PDF_CHARS]

        logger.warning("No paper full text source available for: %s", item.title)
        return ""

    @staticmethod
    def _get_pdf_url(item: SourceItem) -> str:
        """Get PDF URL from item metadata."""
        pdf_url = item.metadata.get("pdf_url", "")
        if pdf_url:
            return pdf_url

        arxiv_id = item.metadata.get("arxiv_id", "")
        if arxiv_id:
            return f"https://arxiv.org/pdf/{arxiv_id}"

        return ""

    async def _extract_pdf_text(self, item: SourceItem, pdf_url: str) -> str:
        logger.info("Downloading PDF for: %s", item.title)
        try:
            pdf_bytes = await self._download_pdf(pdf_url)
        except Exception as e:
            logger.warning("PDF download failed for %s: %s", item.title, e)
            return ""

        try:
            text = self._extract_text(pdf_bytes)
        except Exception as e:
            logger.warning("PDF text extraction failed for %s: %s", item.title, e)
            return ""

        if not text.strip():
            logger.warning("Empty text extracted from PDF: %s", item.title)
            return ""

        logger.info("Extracted %d chars from PDF: %s", len(text[:_MAX_PDF_CHARS]), item.title)
        return text[:_MAX_PDF_CHARS]

    @staticmethod
    async def _download_pdf(url: str) -> bytes:
        """Download PDF from URL."""
        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    @staticmethod
    def _extract_text(pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using pymupdf."""
        import pymupdf

        pages_text: list[str] = []
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp_path = f.name

        try:
            doc = pymupdf.open(tmp_path)
            for page in doc:
                text = page.get_text()
                if text:
                    pages_text.append(text)
            doc.close()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return "\n\n".join(pages_text)

    async def _extract_fallback_text(self, item: SourceItem) -> str:
        for url in self._fallback_source_urls(item):
            try:
                result = await self._fetch_source(url)
            except Exception as exc:
                logger.debug("Paper fallback fetch failed for %s via %s: %s", item.title, url, exc)
                continue

            if result["kind"] == "pdf":
                try:
                    text = self._extract_text(result["content"])
                except Exception as exc:
                    logger.debug("Fallback PDF extraction failed for %s via %s: %s", item.title, url, exc)
                    continue
                if text.strip():
                    return text[:_MAX_PDF_CHARS]
                continue

            html = result["content"].decode("utf-8", errors="ignore")
            pdf_link = self._find_pdf_link(html, result["url"])
            if pdf_link:
                pdf_text = await self._extract_pdf_text(item, pdf_link)
                if pdf_text:
                    return pdf_text

            text = self._html_to_text(html)
            if text:
                return text[:_MAX_PDF_CHARS]

        return ""

    @staticmethod
    async def _fetch_source(url: str) -> dict[str, bytes | str]:
        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": "DailyReport/1.0 (paper fallback fetcher)",
                "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.8",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            kind = "pdf" if "application/pdf" in content_type or resp.url.path.lower().endswith(".pdf") else "html"
            return {"kind": kind, "content": resp.content, "url": str(resp.url)}

    @staticmethod
    def _fallback_source_urls(item: SourceItem) -> list[str]:
        urls: list[str] = []
        doi = item.metadata.get("doi", "")
        if doi:
            urls.append(f"https://doi.org/{doi}")
        if item.url:
            urls.append(item.url)

        deduped: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                deduped.append(url)
        return deduped

    @staticmethod
    def _find_pdf_link(html: str, base_url: str) -> str:
        patterns = [
            r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+property=["\']og:pdf["\'][^>]+content=["\']([^"\']+)["\']',
            r'<a[^>]+href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']',
        ]
        for pattern in patterns:
            import re

            match = re.search(pattern, html, flags=re.IGNORECASE)
            if match:
                return urljoin(base_url, unescape(match.group(1)))
        return ""

    @staticmethod
    def _html_to_text(html: str) -> str:
        parser = _HTMLTextExtractor()
        parser.feed(html)
        return parser.get_text()


class _HTMLTextExtractor(HTMLParser):
    """Very small HTML-to-text fallback for publisher landing pages."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if self._skip_depth == 0 and tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._skip_depth == 0 and tag in {"p", "br", "div", "section", "article", "li"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = " ".join(data.split())
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        text = " ".join(self._parts)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        cleaned = "\n".join(line for line in lines if line)
        return cleaned[:_MAX_PDF_CHARS]
