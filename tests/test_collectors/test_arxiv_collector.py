"""Tests for ArxivCollector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.collectors.arxiv_collector import ArxivCollector
from src.models.source import SourceType
from src.storage.local_store import LocalStore

DUMMY_REQUEST = httpx.Request("GET", "https://example.com")

SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.12345v1</id>
    <title>Test Paper: A Novel Approach</title>
    <summary>We propose a new method for solving problem X.</summary>
    <published>2026-03-10T00:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <category term="cs.AI" />
    <category term="cs.CL" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2603.12346v1</id>
    <title>Another Paper</title>
    <summary>Another abstract.</summary>
    <published>2026-03-09T00:00:00Z</published>
    <author><name>Carol</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
"""

OLD_PAPER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2603.00001v1</id>
    <title>Very Old Paper</title>
    <summary>Old abstract.</summary>
    <published>2025-01-01T00:00:00Z</published>
    <author><name>Old Author</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
"""

SAMPLE_ARXIV_RSS = """<?xml version="1.0"?>
<rdf:RDF
  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns="http://purl.org/rss/1.0/"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://export.arxiv.org/rss/cs.AI">
    <title>arXiv.org cs.AI recent submissions</title>
  </channel>
  <item rdf:about="https://arxiv.org/abs/2603.77777">
    <title>RSS Test Paper [cs.AI] (arXiv:2603.77777v1 [cs.AI])</title>
    <link>https://arxiv.org/abs/2603.77777</link>
    <description>&lt;p&gt;RSS fallback abstract text.&lt;/p&gt;</description>
    <dc:creator>&lt;a href="https://arxiv.org/search/?searchtype=author"&gt;Alice&lt;/a&gt;, &lt;a href="https://arxiv.org/search/?searchtype=author"&gt;Bob&lt;/a&gt;</dc:creator>
    <dc:date>Mon, 10 Mar 2026 00:00:00 GMT</dc:date>
  </item>
</rdf:RDF>
"""


@pytest.fixture
def arxiv_collector(store):
    return ArxivCollector(store, {"categories": ["cs.AI"], "max_results_per_category": 10})


class TestArxivCollector:
    def test_source_name(self, arxiv_collector):
        assert arxiv_collector.source_name == "arxiv"

    @pytest.mark.asyncio
    async def test_collect_parses_xml(self, arxiv_collector):
        mock_response = httpx.Response(200, text=SAMPLE_ARXIV_XML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            items = await arxiv_collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert items[0].source_type == SourceType.ARXIV_PAPER
        assert items[0].title == "Test Paper: A Novel Approach"
        assert items[0].id == "arxiv:2603.12345v1"
        assert "Alice Smith" in items[0].authors
        assert "Bob Jones" in items[0].authors
        assert items[0].metadata["primary_category"] == "cs.AI"

    @pytest.mark.asyncio
    async def test_collect_filters_old_papers(self, arxiv_collector):
        mock_response = httpx.Response(200, text=OLD_PAPER_XML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            items = await arxiv_collector.collect(date(2026, 3, 10))

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_collect_clamps_future_target_date_to_server_date(self, arxiv_collector):
        future_target = date(2026, 3, 30)
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2503.12345v1</id>
    <title>Recent Real-World Paper</title>
    <summary>We propose a practical method.</summary>
    <published>2025-03-28T00:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
"""
        mock_response = httpx.Response(
            200,
            text=xml,
            headers={"Date": "Sun, 30 Mar 2025 12:00:00 GMT"},
            request=DUMMY_REQUEST,
        )
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await arxiv_collector.collect(future_target)

        assert len(items) == 1
        assert items[0].title == "Recent Real-World Paper"

    @pytest.mark.asyncio
    async def test_collect_expands_recent_lookback_when_feed_lags(self, arxiv_collector):
        lagged_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.99999v1</id>
    <title>Weekend Lagged Paper</title>
    <summary>Still recent enough for Monday collection.</summary>
    <published>2026-03-27T17:58:03Z</published>
    <author><name>Alice Smith</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
"""
        mock_response = httpx.Response(
            200,
            text=lagged_xml,
            headers={"Date": "Mon, 30 Mar 2026 06:37:35 GMT"},
            request=DUMMY_REQUEST,
        )
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await arxiv_collector.collect(date(2026, 3, 30))

        assert len(items) == 1
        assert items[0].title == "Weekend Lagged Paper"

    @pytest.mark.asyncio
    async def test_collect_handles_http_error(self, arxiv_collector):
        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPError("Connection failed"),
        ):
            items = await arxiv_collector.collect(date(2026, 3, 10))

        assert items == []

    @pytest.mark.asyncio
    async def test_collect_deduplicates(self, arxiv_collector):
        arxiv_collector.config["categories"] = ["cs.AI", "cs.CL"]
        mock_response = httpx.Response(200, text=SAMPLE_ARXIV_XML, request=DUMMY_REQUEST)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await arxiv_collector.collect(date(2026, 3, 10))

        ids = [item.id for item in items]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_collect_retries_rate_limit_then_recovers(self, arxiv_collector):
        responses = [
            httpx.Response(429, text="Rate exceeded.", request=DUMMY_REQUEST),
            httpx.Response(200, text=SAMPLE_ARXIV_XML, request=DUMMY_REQUEST),
        ]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=responses) as mock_get:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                items = await arxiv_collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert mock_get.await_count == 2
        sleep_calls = [call.args[0] for call in mock_sleep.await_args_list]
        assert 15.0 in sleep_calls

    @pytest.mark.asyncio
    async def test_collect_rate_limit_uses_retry_after_header(self, arxiv_collector):
        responses = [
            httpx.Response(
                429,
                text="Rate exceeded.",
                headers={"Retry-After": "7"},
                request=DUMMY_REQUEST,
            ),
            httpx.Response(200, text=SAMPLE_ARXIV_XML, request=DUMMY_REQUEST),
        ]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=responses):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                items = await arxiv_collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        sleep_calls = [call.args[0] for call in mock_sleep.await_args_list]
        assert 7.0 in sleep_calls

    @pytest.mark.asyncio
    async def test_collect_exhausts_rate_limit_retries(self, arxiv_collector):
        responses = [
            httpx.Response(429, text="Rate exceeded.", request=DUMMY_REQUEST)
            for _ in range(4)
        ]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=responses):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                items = await arxiv_collector.collect(date(2026, 3, 10))

        assert items == []
        sleep_calls = [call.args[0] for call in mock_sleep.await_args_list]
        assert 45.0 in sleep_calls

    @pytest.mark.asyncio
    async def test_collect_reduces_max_results_after_rate_limit(self, store):
        collector = ArxivCollector(
            store,
            {"categories": ["cs.AI"], "max_results_per_category": 50},
        )
        calls: list[int] = []

        async def fake_get(*args, **kwargs):
            calls.append(kwargs["params"]["max_results"])
            if len(calls) == 1:
                return httpx.Response(429, text="Rate exceeded.", request=DUMMY_REQUEST)
            return httpx.Response(200, text=SAMPLE_ARXIV_XML, request=DUMMY_REQUEST)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=fake_get):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert calls == [50, 25]

    @pytest.mark.asyncio
    async def test_collect_uses_direct_network_mode(self, store):
        collector = ArxivCollector(
            store,
            {"categories": ["cs.AI"], "max_results_per_category": 10},
        )
        captured_kwargs: dict[str, object] = {}

        class FakeClient:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, *args, **kwargs):
                return httpx.Response(200, text=SAMPLE_ARXIV_XML, request=DUMMY_REQUEST)

        with patch("httpx.AsyncClient", FakeClient):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                items = await collector.collect(date(2026, 3, 10))

        assert len(items) == 2
        assert captured_kwargs["trust_env"] is False

    def test_parse_atom_response(self, arxiv_collector):
        items = arxiv_collector._parse_atom_response(SAMPLE_ARXIV_XML, "cs.AI", date(2026, 3, 8))
        assert len(items) == 2
        assert items[0].url.startswith("https://arxiv.org/abs/")

    def test_parse_invalid_xml(self, arxiv_collector):
        items = arxiv_collector._parse_atom_response("not xml", "cs.AI", date(2026, 3, 8))
        assert items == []

    def test_parse_rss_fallback_response(self, arxiv_collector):
        items = arxiv_collector._parse_rss_response(SAMPLE_ARXIV_RSS, "cs.AI", date(2026, 3, 8))
        assert len(items) == 1
        assert items[0].title == "RSS Test Paper"
        assert items[0].metadata["ingest_source"] == "rss_fallback"
        assert items[0].authors == ["Alice", "Bob"]
