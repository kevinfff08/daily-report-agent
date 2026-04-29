"""LLM client wrapper supporting Anthropic, OpenAI, and DeepSeek APIs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

import httpx
from anthropic import Anthropic, APIStatusError

from src.logging_config import get_logger
from src.utils.json_repair import repair_json

logger = get_logger("llm.client")

_PROMPTS_DIR = Path(__file__).parent / "prompts" / "v1"

# Retry config for transient API errors (429, 529, 500, 502, 503)
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0  # seconds
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}
_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
_OPENAI_TIMEOUT_SECONDS = 180.0


def _default_model(provider: str) -> str:
    """Return provider-specific default model."""
    if provider == "openai":
        return "gpt-4.1-mini"
    if provider == "deepseek":
        return "deepseek-v4-flash"
    return "claude-sonnet-4-20250514"


def _default_base_url(provider: str) -> str:
    """Return provider-specific default base URL for HTTP clients."""
    if provider == "deepseek":
        return _DEEPSEEK_BASE_URL
    return _OPENAI_BASE_URL


def _normalize_openai_base_url(base_url: str) -> str:
    """Normalize OpenAI-compatible base URL to include /v1."""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


class LLMClient:
    """Wrapper around supported LLM APIs."""

    def __init__(
        self,
        provider: Literal["anthropic", "openai", "deepseek"] = "anthropic",
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.provider = provider.lower()
        if self.provider not in {"anthropic", "openai", "deepseek"}:
            raise ValueError(f"Unsupported LLM provider: {provider}")

        # In proxy mode (base_url set), use a placeholder key if none provided
        if base_url and not api_key:
            self.api_key = "placeholder-for-proxy"
        else:
            self.api_key = api_key or ""
        self.model = model or _default_model(self.provider)
        if self.provider in {"openai", "deepseek"} and base_url:
            self.base_url = _normalize_openai_base_url(base_url)
        else:
            self.base_url = base_url
        self._client: Anthropic | httpx.Client | None = None

    @property
    def client(self) -> Anthropic | httpx.Client:
        if self._client is None:
            if self.provider == "anthropic":
                kwargs: dict[str, Any] = {"api_key": self.api_key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                self._client = Anthropic(**kwargs)
            else:
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                resolved_base_url = self.base_url or _default_base_url(self.provider)
                resolved_base_url = _normalize_openai_base_url(resolved_base_url)
                self._client = httpx.Client(
                    base_url=resolved_base_url.rstrip("/") + "/",
                    headers=headers,
                    timeout=_OPENAI_TIMEOUT_SECONDS,
                )
        return self._client

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.3,
    ) -> str:
        """Generate text from the configured provider."""
        logger.debug(
            "LLM request: provider=%s, model=%s, max_tokens=%d, temp=%.1f, prompt_preview=%.100s...",
            self.provider, self.model, max_tokens, temperature, prompt[:100],
        )
        t0 = time.time()

        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                if self.provider == "anthropic":
                    return self._generate_anthropic(prompt, system, max_tokens, temperature, t0)
                return self._generate_openai_compatible(prompt, system, max_tokens, temperature, t0)
            except APIStatusError as e:
                last_err = e
                status_code = e.status_code
                message = e.message
            except httpx.HTTPStatusError as e:
                last_err = e
                status_code = e.response.status_code
                message = e.response.text[:200]

            if status_code not in _RETRYABLE_STATUS_CODES:
                raise last_err

            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "LLM API error %d (provider=%s, attempt %d/%d), retrying in %.0fs: %s",
                status_code, self.provider, attempt + 1, _MAX_RETRIES, delay, message,
            )
            time.sleep(delay)

        raise last_err  # type: ignore[misc]

    def _generate_anthropic(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        temperature: float,
        t0: float,
    ) -> str:
        """Generate text via Anthropic Messages API."""
        client = self.client

        messages = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        text = response.content[0].text

        latency = time.time() - t0
        logger.debug(
            "LLM response: provider=anthropic, latency=%.1fs, input=%d, output=%d, stop=%s",
            latency,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.stop_reason,
        )
        return text

    def _generate_openai_compatible(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        temperature: float,
        t0: float,
    ) -> str:
        """Generate text via an OpenAI-compatible Chat Completions API."""
        client = self.client

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        request_body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.provider == "deepseek":
            # Keep current text/JSON workflows stable by opting out of DeepSeek's
            # default thinking mode unless a future dedicated feature enables it.
            request_body["thinking"] = {"type": "disabled"}

        response = client.post(
            "chat/completions",
            json=request_body,
        )
        response.raise_for_status()

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("OpenAI response missing choices")

        message = choices[0].get("message", {})
        text = self._extract_openai_text(message.get("content"))
        if not text:
            raise ValueError("OpenAI response contains empty content")

        usage = data.get("usage", {})
        latency = time.time() - t0
        logger.debug(
            "LLM response: provider=%s, latency=%.1fs, input=%s, output=%s, stop=%s",
            self.provider,
            latency,
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            choices[0].get("finish_reason"),
        )
        return text

    @staticmethod
    def _extract_openai_text(content: Any) -> str:
        """Extract plain text from OpenAI message content."""
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for chunk in content:
                if not isinstance(chunk, dict):
                    continue

                text = chunk.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, dict):
                    value = text.get("value")
                    if isinstance(value, str):
                        parts.append(value)

            return "\n".join(parts).strip()

        return ""

    def generate_json(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.1,
    ) -> dict | list | None:
        """Generate and parse JSON from the configured provider."""
        json_system = (system + "\n\n" if system else "") + (
            "You MUST respond with valid JSON only. No markdown fences, no explanation, just JSON."
        )
        text = self.generate(prompt, system=json_system, max_tokens=max_tokens, temperature=temperature)
        result = repair_json(text)
        if result is None:
            logger.warning("Failed to parse JSON from LLM response: %.200s...", text[:200])
        return result

    def generate_with_template(
        self,
        template_name: str,
        variables: dict,
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.3,
    ) -> str:
        """Generate text using a prompt template file."""
        template_path = _PROMPTS_DIR / f"{template_name}.txt"
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        template = template_path.read_text(encoding="utf-8")
        prompt = template.format(**variables)
        return self.generate(prompt, system=system, max_tokens=max_tokens, temperature=temperature)

    def generate_json_with_template(
        self,
        template_name: str,
        variables: dict,
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.1,
    ) -> dict | list | None:
        """Generate JSON using a prompt template file."""
        template_path = _PROMPTS_DIR / f"{template_name}.txt"
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        template = template_path.read_text(encoding="utf-8")
        prompt = template.format(**variables)
        return self.generate_json(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
