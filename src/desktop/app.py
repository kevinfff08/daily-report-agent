"""pywebview desktop shell for DailyReport."""

from __future__ import annotations

import os
import importlib
from datetime import date
from pathlib import Path
from typing import Any

from src.desktop.api import DailyReportDesktopAPI


class DesktopDependencyError(RuntimeError):
    """Raised when the optional desktop runtime is unavailable."""


def _load_shell_html() -> str:
    """Read the packaged desktop shell HTML."""
    shell_path = Path(__file__).parent / "static" / "shell.html"
    return shell_path.read_text(encoding="utf-8")


def _import_webview() -> Any:
    """Import pywebview with a user-facing error if it is missing."""
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DesktopDependencyError(
            "pywebview is not installed. Install the desktop dependencies in the "
            "research_tools environment, then run start_app.bat again. On Windows "
            "Python 3.14, use the Qt backend dependencies: "
            "python -m pip install --no-deps pywebview bottle proxy_tools QtPy PySide6"
        ) from exc
    return webview


def _ensure_backend_runtime(gui: str | None) -> None:
    """Fail early with a clear message when the selected webview backend is absent."""
    if gui != "qt":
        return

    missing = [
        module
        for module in ("qtpy", "PySide6")
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise DesktopDependencyError(
            "The DailyReport desktop app uses pywebview's Qt backend by default, "
            f"but these packages are missing: {', '.join(missing)}. Install them "
            "inside the research_tools environment with: "
            "python -m pip install QtPy PySide6"
        )


def _prepare_backend_environment(gui: str | None) -> None:
    """Set backend-specific environment defaults before pywebview starts."""
    if gui == "qt":
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        os.environ.setdefault("QT_OPENGL", "software")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        chromium_flags = [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-gpu-compositing",
            "--disable-accelerated-2d-canvas",
            "--disable-zero-copy",
            "--disable-features=CanvasOopRasterization,VizDisplayCompositor",
        ]
        existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        merged_flags = existing_flags.split()
        for flag in chromium_flags:
            if flag not in merged_flags:
                merged_flags.append(flag)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(merged_flags).strip()


def launch_desktop_app(default_date: date | None = None) -> None:
    """Launch the local pywebview desktop app."""
    webview = _import_webview()
    api = DailyReportDesktopAPI(default_date=default_date)
    debug = os.environ.get("DAILYREPORT_APP_DEBUG", "").strip() == "1"
    gui = os.environ.get("DAILYREPORT_WEBVIEW_GUI", "qt").strip() or None
    _ensure_backend_runtime(gui)
    _prepare_backend_environment(gui)
    webview.create_window(
        "DailyReport",
        html=_load_shell_html(),
        js_api=api,
        width=1480,
        height=940,
        min_size=(1080, 720),
        confirm_close=True,
        text_select=True,
    )
    try:
        webview.start(gui=gui, debug=debug)
    except Exception as exc:
        if exc.__class__.__name__ == "WebViewException":
            raise DesktopDependencyError(
                f"pywebview backend failed ({gui or 'default'}): {exc}. "
                "The default DailyReport desktop backend is Qt. To force another "
                "backend, set DAILYREPORT_WEBVIEW_GUI before running start_app.bat."
            ) from exc
        raise
