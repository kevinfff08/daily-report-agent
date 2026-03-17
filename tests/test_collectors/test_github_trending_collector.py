"""Tests for GitHubTrendingCollector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.github_trending_collector import GitHubTrendingCollector
from src.models.source import SourceType

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")

SAMPLE_TRENDING_HTML = """
<html><body>
<article class="Box-row">
  <h2><a href="/owner1/cool-project">owner1 / cool-project</a></h2>
  <p>An amazing AI framework for building agents</p>
  <a href="/owner1/cool-project/stargazers"> 5,000 </a>
  <span itemprop="programmingLanguage">Python</span>
  <span>200 stars today</span>
</article>
<article class="Box-row">
  <h2><a href="/owner2/ml-toolkit">owner2 / ml-toolkit</a></h2>
  <p>Machine learning utilities</p>
  <a href="/owner2/ml-toolkit/stargazers"> 1,200 </a>
  <span itemprop="programmingLanguage">Rust</span>
  <span>50 stars today</span>
</article>
</body></html>
"""


@pytest.fixture
def gh_config():
    return {
        "languages": ["python"],
        "since": "daily",
        "max_items": 30,
    }


@pytest.fixture
def gh_collector(store, gh_config):
    return GitHubTrendingCollector(store, gh_config)


class TestGitHubTrendingCollector:
    @pytest.mark.asyncio
    async def test_collect_success(self, gh_collector):
        resp = httpx.Response(200, text=SAMPLE_TRENDING_HTML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
            items = await gh_collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert items[0].source_type == SourceType.GITHUB_TRENDING
        assert items[0].id == "github:owner1/cool-project"
        assert items[0].title == "owner1/cool-project"
        assert "github.com" in items[0].url

    @pytest.mark.asyncio
    async def test_max_items(self, store):
        collector = GitHubTrendingCollector(store, {
            "languages": ["python"],
            "since": "daily",
            "max_items": 1,
        })
        resp = httpx.Response(200, text=SAMPLE_TRENDING_HTML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
            items = await collector.collect(date(2026, 3, 10))

        assert len(items) <= 1

    @pytest.mark.asyncio
    async def test_api_error(self, gh_collector):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock,
                    side_effect=httpx.HTTPError("Error")):
            items = await gh_collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_empty_html(self, gh_collector):
        resp = httpx.Response(200, text="<html><body></body></html>", request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
            items = await gh_collector.collect(date(2026, 3, 10))
        assert items == []

    def test_parse_trending_html(self, gh_collector):
        items = gh_collector._parse_trending_html(SAMPLE_TRENDING_HTML, date(2026, 3, 10))
        assert len(items) == 2
        assert items[0].metadata["owner"] == "owner1"
        assert items[0].metadata["repo_name"] == "cool-project"
