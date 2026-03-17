"""Tests for ProductHuntCollector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.product_hunt_collector import ProductHuntCollector
from src.models.source import SourceType

DUMMY_REQUEST = httpx.Request("POST", "https://example.com")

GRAPHQL_RESPONSE = {
    "data": {
        "posts": {
            "edges": [
                {
                    "node": {
                        "id": "12345",
                        "name": "AI Assistant Pro",
                        "tagline": "Your personal AI assistant",
                        "description": "The best AI assistant for productivity.",
                        "url": "https://www.producthunt.com/posts/ai-assistant-pro",
                        "votesCount": 300,
                        "createdAt": "2026-03-10T07:00:00Z",
                        "website": "https://ai-assistant.pro",
                        "topics": {
                            "edges": [
                                {"node": {"name": "Artificial Intelligence"}},
                            ]
                        },
                        "makers": [{"name": "Maker One"}],
                    }
                },
                {
                    "node": {
                        "id": "12346",
                        "name": "ML Pipeline Tool",
                        "tagline": "Automate your ML pipelines",
                        "description": "Easy ML pipeline management.",
                        "url": "https://www.producthunt.com/posts/ml-pipeline-tool",
                        "votesCount": 150,
                        "createdAt": "2026-03-10T09:00:00Z",
                        "website": "https://ml-pipeline.io",
                        "topics": {"edges": []},
                        "makers": [],
                    }
                },
            ]
        }
    }
}


@pytest.fixture
def ph_config():
    return {
        "topics": ["artificial-intelligence"],
        "max_items": 20,
    }


@pytest.fixture
def ph_collector(store, ph_config):
    return ProductHuntCollector(store, ph_config)


class TestProductHuntCollector:
    @pytest.mark.asyncio
    async def test_collect_success(self, ph_collector):
        resp = httpx.Response(200, json=GRAPHQL_RESPONSE, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=resp):
            with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test-token"}):
                items = await ph_collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert items[0].source_type == SourceType.PRODUCT_HUNT
        assert items[0].id == "ph:12345"
        assert items[0].title == "AI Assistant Pro"
        assert items[0].metadata["votes_count"] == 300

    @pytest.mark.asyncio
    async def test_no_token(self, ph_collector):
        with patch.dict("os.environ", {}, clear=True):
            items = await ph_collector.collect(date(2026, 3, 10))
        assert items == []

    @pytest.mark.asyncio
    async def test_api_error(self, ph_collector):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock,
                    side_effect=httpx.HTTPError("Error")):
            with patch.dict("os.environ", {"PRODUCT_HUNT_TOKEN": "test-token"}):
                items = await ph_collector.collect(date(2026, 3, 10))
        assert items == []
