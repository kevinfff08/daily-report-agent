"""Tests for LLM client retry logic across providers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from anthropic import APIStatusError

from src.llm.client import LLMClient


def _make_api_status_error(status_code: int) -> APIStatusError:
    """Create an APIStatusError with the given status code."""
    resp = httpx.Response(
        status_code=status_code,
        json={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    return APIStatusError(message="Overloaded", response=resp, body=resp.json())


def _make_success_response(text: str = "hello") -> MagicMock:
    """Create a mock successful API response."""
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    resp.stop_reason = "end_turn"
    return resp


def _make_openai_response(
    status_code: int = 200,
    text: str = "hello",
    content: str | list[dict] | None = None,
) -> httpx.Response:
    """Create an OpenAI-style chat completion response."""
    message_content = content if content is not None else text
    payload = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": message_content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
    }
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )


class TestLLMClientAnthropicRetry:
    """Test Anthropic retry behavior on transient API errors."""

    @patch("src.llm.client._RETRY_BASE_DELAY", 0.01)
    def test_retry_on_529_then_succeed(self) -> None:
        """Should retry on 529 and succeed on next attempt."""
        client = LLMClient(api_key="test-key")
        mock_create = MagicMock(
            side_effect=[
                _make_api_status_error(529),
                _make_success_response("ok"),
            ]
        )
        with patch.object(client, "_client", create=True) as mock_anthropic:
            mock_anthropic.messages.create = mock_create
            result = client.generate("test prompt")

        assert result == "ok"
        assert mock_create.call_count == 2

    @patch("src.llm.client._RETRY_BASE_DELAY", 0.01)
    def test_retry_on_429_then_succeed(self) -> None:
        """Should retry on 429 rate limit."""
        client = LLMClient(api_key="test-key")
        mock_create = MagicMock(
            side_effect=[
                _make_api_status_error(429),
                _make_api_status_error(429),
                _make_success_response("done"),
            ]
        )
        with patch.object(client, "_client", create=True) as mock_anthropic:
            mock_anthropic.messages.create = mock_create
            result = client.generate("test prompt")

        assert result == "done"
        assert mock_create.call_count == 3

    @patch("src.llm.client._RETRY_BASE_DELAY", 0.01)
    @patch("src.llm.client._MAX_RETRIES", 3)
    def test_exhausted_retries_raises(self) -> None:
        """Should raise after exhausting all retries."""
        client = LLMClient(api_key="test-key")
        mock_create = MagicMock(
            side_effect=[_make_api_status_error(529)] * 3
        )
        with patch.object(client, "_client", create=True) as mock_anthropic:
            mock_anthropic.messages.create = mock_create
            with pytest.raises(APIStatusError) as exc_info:
                client.generate("test prompt")
            assert exc_info.value.status_code == 529

    def test_non_retryable_error_raises_immediately(self) -> None:
        """Should NOT retry on 400 Bad Request."""
        client = LLMClient(api_key="test-key")
        mock_create = MagicMock(
            side_effect=_make_api_status_error(400)
        )
        with patch.object(client, "_client", create=True) as mock_anthropic:
            mock_anthropic.messages.create = mock_create
            with pytest.raises(APIStatusError) as exc_info:
                client.generate("test prompt")
            assert exc_info.value.status_code == 400
        assert mock_create.call_count == 1

    def test_no_retry_on_success(self) -> None:
        """Normal success should not trigger any retry."""
        client = LLMClient(api_key="test-key")
        mock_create = MagicMock(return_value=_make_success_response("hi"))
        with patch.object(client, "_client", create=True) as mock_anthropic:
            mock_anthropic.messages.create = mock_create
            result = client.generate("test prompt")

        assert result == "hi"
        assert mock_create.call_count == 1


class TestLLMClientOpenAI:
    """Test OpenAI provider behavior."""

    def test_openai_default_base_url(self) -> None:
        """OpenAI client should target the /v1 base URL by default."""
        client = LLMClient(provider="openai", api_key="test-key")
        openai_client = client.client
        assert isinstance(openai_client, httpx.Client)
        assert str(openai_client.base_url) == "https://api.openai.com/v1/"
        openai_client.close()

    def test_openai_proxy_base_url_is_normalized_to_v1(self) -> None:
        """OpenAI proxy URL without /v1 should be normalized automatically."""
        client = LLMClient(
            provider="openai",
            api_key="test-key",
            base_url="http://localhost:8317",
        )
        openai_client = client.client
        assert isinstance(openai_client, httpx.Client)
        assert str(openai_client.base_url) == "http://localhost:8317/v1/"
        openai_client.close()

    def test_openai_proxy_base_url_keeps_existing_v1(self) -> None:
        """OpenAI proxy URL with /v1 should not be duplicated."""
        client = LLMClient(
            provider="openai",
            api_key="test-key",
            base_url="http://localhost:8317/v1/",
        )
        openai_client = client.client
        assert isinstance(openai_client, httpx.Client)
        assert str(openai_client.base_url) == "http://localhost:8317/v1/"
        openai_client.close()

    @patch("src.llm.client._RETRY_BASE_DELAY", 0.01)
    def test_retry_on_429_then_succeed(self) -> None:
        """Should retry on 429 rate limits for OpenAI."""
        client = LLMClient(provider="openai", api_key="test-key", model="gpt-4.1-mini")
        mock_post = MagicMock(
            side_effect=[
                _make_openai_response(status_code=429, text="rate limited"),
                _make_openai_response(status_code=200, text="ok"),
            ]
        )
        with patch.object(client, "_client", create=True) as mock_openai:
            mock_openai.post = mock_post
            result = client.generate("test prompt")

        assert result == "ok"
        assert mock_post.call_count == 2

    def test_non_retryable_error_raises_immediately(self) -> None:
        """Should NOT retry on 400 Bad Request for OpenAI."""
        client = LLMClient(provider="openai", api_key="test-key", model="gpt-4.1-mini")
        mock_post = MagicMock(return_value=_make_openai_response(status_code=400, text="bad request"))
        with patch.object(client, "_client", create=True) as mock_openai:
            mock_openai.post = mock_post
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                client.generate("test prompt")
            assert exc_info.value.response.status_code == 400

        assert mock_post.call_count == 1

    def test_extracts_text_from_structured_content(self) -> None:
        """Should extract text when OpenAI returns list content blocks."""
        client = LLMClient(provider="openai", api_key="test-key", model="gpt-4.1-mini")
        structured_content = [
            {"type": "text", "text": "part one"},
            {"type": "text", "text": {"value": "part two"}},
        ]
        mock_post = MagicMock(return_value=_make_openai_response(content=structured_content))
        with patch.object(client, "_client", create=True) as mock_openai:
            mock_openai.post = mock_post
            result = client.generate("test prompt")

        assert result == "part one\npart two"

    def test_openai_default_model(self) -> None:
        """OpenAI provider should use provider-specific default model."""
        client = LLMClient(provider="openai", api_key="test-key")
        assert client.model == "gpt-4.1-mini"
