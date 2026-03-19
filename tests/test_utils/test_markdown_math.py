"""Tests for Markdown math delimiter normalization."""

from src.utils.markdown_math import normalize_markdown_math


def test_normalize_inline_and_block_math() -> None:
    text = (
        "Inline: \\(a+b\\)\n\n"
        "\\[\n"
        "\\frac{1}{2}\n"
        "\\]\n"
    )

    out = normalize_markdown_math(text)

    assert "Inline: $a+b$" in out
    assert "$$\n\\frac{1}{2}\n$$" in out


def test_keep_code_fence_unchanged() -> None:
    text = (
        "Normal \\(x\\)\n\n"
        "```latex\n"
        "\\(should_not_change\\)\n"
        "\\[should_not_change\\]\n"
        "```\n"
    )

    out = normalize_markdown_math(text)

    assert "Normal $x$" in out
    assert "\\(should_not_change\\)" in out
    assert "\\[should_not_change\\]" in out
