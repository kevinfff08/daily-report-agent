from __future__ import annotations

from pathlib import Path


def test_shell_embeds_registry_markdown_write_bridge() -> None:
    shell_html = Path("src/desktop/static/shell.html").read_text(encoding="utf-8")

    assert "prepareEmbeddedRegistryWriteBack" in shell_html
    assert "writeEmbeddedRegistryStatuses" in shell_html
    assert "update_registry_status" in shell_html
    assert "collectEmbeddedRegistryUpdates" in shell_html
