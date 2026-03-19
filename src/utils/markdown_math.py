"""Helpers for normalizing math delimiters in Markdown reports."""

from __future__ import annotations

import re

_CODE_FENCE_PATTERN = re.compile(r"(```[\s\S]*?```)")
_BLOCK_MATH_PATTERN = re.compile(r"\\\[\s*([\s\S]*?)\s*\\\]")
_INLINE_MATH_PATTERN = re.compile(r"\\\((.*?)\\\)")


def normalize_markdown_math(text: str) -> str:
    """Convert LaTeX \\(...\\)/\\[...\\] delimiters to $...$/$$...$$.

    The transformation is skipped inside fenced code blocks.
    """
    parts = _CODE_FENCE_PATTERN.split(text)
    normalized: list[str] = []

    for i, part in enumerate(parts):
        if i % 2 == 1:  # fenced code block
            normalized.append(part)
            continue

        part = _BLOCK_MATH_PATTERN.sub(_replace_block_math, part)
        part = _INLINE_MATH_PATTERN.sub(_replace_inline_math, part)
        normalized.append(part)

    return "".join(normalized)


def _replace_block_math(match: re.Match[str]) -> str:
    expr = match.group(1).strip()
    return f"$$\n{expr}\n$$"


def _replace_inline_math(match: re.Match[str]) -> str:
    expr = match.group(1).strip()
    return f"${expr}$"
