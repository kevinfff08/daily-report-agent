"""Claude API client wrapper."""

from __future__ import annotations

import time
from pathlib import Path

from anthropic import Anthropic

from src.logging_config import get_logger
from src.utils.json_repair import repair_json

logger = get_logger("llm.client")

_PROMPTS_DIR = Path(__file__).parent / "prompts" / "v1"


class LLMClient:
    """Wrapper around the Anthropic Claude API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
    ):
        self.api_key = api_key or ""
        self.model = model
        self.base_url = base_url
        self._client: Anthropic | None = None

    @property
    def client(self) -> Anthropic:
        if self._client is None:
            kwargs: dict = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = Anthropic(**kwargs)
        return self._client

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.3,
    ) -> str:
        """Generate text from Claude."""
        logger.debug(
            "LLM request: model=%s, max_tokens=%d, temp=%.1f, prompt_preview=%.100s...",
            self.model, max_tokens, temperature, prompt[:100],
        )
        t0 = time.time()

        messages = [{"role": "user", "content": prompt}]
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        text = response.content[0].text

        latency = time.time() - t0
        logger.debug(
            "LLM response: latency=%.1fs, input=%d, output=%d, stop=%s",
            latency,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.stop_reason,
        )
        return text

    def generate_json(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.1,
    ) -> dict | list | None:
        """Generate and parse JSON from Claude."""
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
