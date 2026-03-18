"""Tests for LLM client retry logic."""

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


class TestLLMClientRetry:
    """Test retry behavior on transient API errors."""

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
