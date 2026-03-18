"""Paper enricher: downloads arXiv PDFs and extracts full text."""

from __future__ import annotations

import tempfile
from pathlib import Path

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
        if not pdf_url:
            logger.warning("No PDF URL for paper: %s", item.title)
            return ""

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

        logger.info(
            "Extracted %d chars from PDF: %s",
            len(text[:_MAX_PDF_CHARS]), item.title,
        )
        return text[:_MAX_PDF_CHARS]

    @staticmethod
    def _get_pdf_url(item: SourceItem) -> str:
        """Get PDF URL from item metadata."""
        # arXiv items have pdf_url in metadata
        pdf_url = item.metadata.get("pdf_url", "")
        if pdf_url:
            return pdf_url

        # Semantic Scholar items may have arxiv_id
        arxiv_id = item.metadata.get("arxiv_id", "")
        if arxiv_id:
            return f"https://arxiv.org/pdf/{arxiv_id}"

        return ""

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
