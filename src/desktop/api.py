"""Python bridge API used by the pywebview desktop shell."""

from __future__ import annotations

import asyncio
import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from src.logging_config import get_logger
from src.models.registry import InterestStatus
from src.models.source import SourceType
from src.storage.local_store import LocalStore
from src.storage.registry_store import RegistryStore

logger = get_logger("desktop.api")

_ALLOWED_ACTIONS = {
    "collect",
    "report",
    "run",
    "deep_dive",
    "html",
    "registry_html",
}
_REPORT_KINDS = {
    "overview": ("daily_report.html", "overview.html"),
    "daily": ("daily_report.html", "overview.html"),
    "deep_dive": ("deep_dive_report.html", "deep_dive.html"),
    "deep-dive": ("deep_dive_report.html", "deep_dive.html"),
}
_CATEGORY_LABELS = {
    SourceType.ARXIV_PAPER.value: "\u8bba\u6587",
    SourceType.SEMANTIC_SCHOLAR.value: "\u8bba\u6587",
    SourceType.TAVILY_SEARCH.value: "\u4e1a\u754c\u52a8\u6001",
    SourceType.PRODUCT_HUNT.value: "\u4e1a\u754c\u52a8\u6001",
    SourceType.HACKER_NEWS.value: "\u793e\u533a\u70ed\u70b9",
    SourceType.YOUTUBE_VIDEO.value: "\u793e\u533a\u70ed\u70b9",
    SourceType.BILIBILI_VIDEO.value: "\u793e\u533a\u70ed\u70b9",
    SourceType.GITHUB_TRENDING.value: "\u793e\u533a\u70ed\u70b9",
}
_STATUS_TOKEN_MAP = {
    "star": InterestStatus.STAR,
    "*": InterestStatus.STAR,
    "question": InterestStatus.QUESTION,
    "?": InterestStatus.QUESTION,
    "check": InterestStatus.CHECK,
    "\u2713": InterestStatus.CHECK,
    "none": InterestStatus.NONE,
    "": InterestStatus.NONE,
}


@dataclass
class JobState:
    """Serializable state for one desktop background job."""

    job_id: str
    action: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    started_at: str | None = None
    finished_at: str | None = None
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot."""
        return {
            "job_id": self.job_id,
            "action": self.action,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "logs": list(self.logs),
            "result": self.result,
            "error": self.error,
        }


class DailyReportDesktopAPI:
    """Bridge object exposed to JavaScript by pywebview."""

    def __init__(
        self,
        default_date: date | str | None = None,
        *,
        orchestrator_factory: Callable[[], Any] | None = None,
        registry_store_factory: Callable[[], RegistryStore] | None = None,
        project_root: str | Path | None = None,
    ) -> None:
        self.default_date = _parse_date(default_date) if default_date else date.today()
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self._orchestrator_factory = orchestrator_factory
        self._registry_store_factory = registry_store_factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dailyreport-desktop")
        self._lock = threading.Lock()
        self._jobs: dict[str, JobState] = {}

    # --- Public bridge methods ---

    def get_status(self) -> dict[str, Any]:
        """Return config and local artifact status for the shell."""
        try:
            orch = self._make_orchestrator()
            info = orch.get_status()
            return {
                "ok": True,
                "defaultDate": self.default_date.isoformat(),
                "defaultMonth": self.default_date.strftime("%Y-%m"),
                "system": info,
                "reports": self._report_state(self.default_date),
            }
        except Exception as exc:
            logger.exception("Desktop status failed")
            return {
                "ok": False,
                "defaultDate": self.default_date.isoformat(),
                "defaultMonth": self.default_date.strftime("%Y-%m"),
                "error": str(exc),
                "reports": self._report_state(self.default_date),
            }

    def start_task(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start a whitelisted background task and return its job id."""
        normalized_action = action.strip().lower().replace("-", "_")
        if normalized_action not in _ALLOWED_ACTIONS:
            return {"ok": False, "error": f"Unsupported desktop action: {action}"}
        if payload is not None and not isinstance(payload, dict):
            return {"ok": False, "error": "Task payload must be an object."}

        with self._lock:
            active = next(
                (
                    job
                    for job in self._jobs.values()
                    if job.status in {"queued", "running"}
                ),
                None,
            )
            if active is not None:
                return {
                    "ok": False,
                    "error": f"Another task is already {active.status}: {active.action}",
                    "active_job_id": active.job_id,
                }

            job = JobState(job_id=uuid4().hex, action=normalized_action)
            self._jobs[job.job_id] = job

        self._executor.submit(self._run_job, job.job_id, normalized_action, payload or {})
        return {"ok": True, "job_id": job.job_id}

    def get_job(self, job_id: str) -> dict[str, Any]:
        """Return the latest state for one background job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return {"ok": False, "error": f"Unknown job: {job_id}"}
            return {"ok": True, "job": job.to_dict()}

    def list_items(self, target_date: str | None = None) -> dict[str, Any]:
        """Load overview item choices from items_index.json."""
        try:
            d = _parse_date(target_date) if target_date else self.default_date
            store = self._make_store()
            entries = store.load_json(store.layer_relative_path("reports", d, "items_index.json"))
            if not entries:
                return {
                    "ok": True,
                    "date": d.isoformat(),
                    "items": [],
                    "message": "No items_index.json found. Generate the overview first.",
                }
            if not isinstance(entries, list):
                return {"ok": False, "error": "items_index.json is not a list."}

            items = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                source_item = entry.get("source_item")
                if not isinstance(source_item, dict):
                    continue
                index = _coerce_int(entry.get("index"))
                if index is None:
                    continue
                source_type = str(source_item.get("source_type") or "")
                metadata = source_item.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                items.append({
                    "index": index,
                    "indexLabel": f"{index:03d}",
                    "title": str(source_item.get("title") or ""),
                    "url": str(source_item.get("url") or ""),
                    "sourceType": source_type,
                    "category": _CATEGORY_LABELS.get(source_type, source_type or "\u672a\u77e5"),
                    "source": str(metadata.get("source_name") or source_type or ""),
                })

            return {"ok": True, "date": d.isoformat(), "items": items}
        except Exception as exc:
            logger.exception("Loading desktop items failed")
            return {"ok": False, "error": str(exc)}

    def load_report(self, kind: str, target_date: str | None = None) -> dict[str, Any]:
        """Load an overview or deep-dive HTML report for display."""
        try:
            d = _parse_date(target_date) if target_date else self.default_date
            candidates = self._report_candidates(kind, d)
            for path in candidates:
                if path.exists():
                    return self._load_html_response(path, date_label=d.isoformat(), kind=kind)
            return {
                "ok": False,
                "error": f"No {kind} HTML report found for {d.isoformat()}.",
                "path": str(candidates[0]) if candidates else "",
            }
        except Exception as exc:
            logger.exception("Loading desktop report failed")
            return {"ok": False, "error": str(exc)}

    def load_registry(self, month: str | None = None) -> dict[str, Any]:
        """Load a monthly registry HTML file for display."""
        try:
            resolved_month = _parse_month(month, self.default_date)
            path = self._registry_dir() / f"{resolved_month}-record.html"
            if not path.exists():
                return {
                    "ok": False,
                    "error": f"No registry HTML found for {resolved_month}. Generate registry HTML first.",
                    "path": str(path),
                }
            return self._load_html_response(path, date_label=resolved_month, kind="registry")
        except Exception as exc:
            logger.exception("Loading desktop registry failed")
            return {"ok": False, "error": str(exc)}

    def update_registry_status(
        self,
        record_id: str,
        statuses: list[str] | str | None,
        mode: str = "set",
    ) -> dict[str, Any]:
        """Update a registry entry's user-maintained interest statuses."""
        try:
            normalized_mode = mode.strip().lower()
            if normalized_mode not in {"add", "set", "remove", "clear"}:
                return {"ok": False, "error": f"Unsupported registry status mode: {mode}"}
            parsed = _parse_statuses(statuses)
            if normalized_mode == "clear":
                parsed = []
            elif not parsed:
                normalized_mode = "clear"

            store = self._make_registry_store()
            entry = store.update_interest_statuses(record_id.strip(), parsed, mode=normalized_mode)
            html_path = store.render_month_html(entry.month_key)
            return {
                "ok": True,
                "recordId": entry.record_id,
                "statuses": [status.value for status in entry.interest_statuses],
                "statusDisplay": entry.interest_status_display,
                "month": entry.month_key,
                "htmlPath": str(_resolve_against(self.project_root, html_path)),
            }
        except KeyError:
            return {"ok": False, "error": f"Registry entry not found: {record_id}"}
        except Exception as exc:
            logger.exception("Updating registry status failed")
            return {"ok": False, "error": str(exc)}

    # --- Background jobs ---

    def _run_job(self, job_id: str, action: str, payload: dict[str, Any]) -> None:
        self._set_job_running(job_id)
        try:
            result = self._dispatch_action(job_id, action, payload)
        except Exception as exc:
            logger.exception("Desktop job failed: %s", action)
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = datetime.now().isoformat(timespec="seconds")
                job.logs.append(traceback.format_exc(limit=5))
            return

        with self._lock:
            job = self._jobs[job_id]
            job.status = "succeeded"
            job.result = result
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            job.logs.append("Task completed.")

    def _set_job_running(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = datetime.now().isoformat(timespec="seconds")
            job.logs.append("Task started.")

    def _job_log(self, job_id: str, message: str) -> None:
        with self._lock:
            self._jobs[job_id].logs.append(message)

    def _dispatch_action(self, job_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "collect":
            return self._run_collect(job_id, payload)
        if action == "report":
            return self._run_report(job_id, payload)
        if action == "run":
            return self._run_pipeline(job_id, payload)
        if action == "deep_dive":
            return self._run_deep_dive(job_id, payload)
        if action == "html":
            return self._run_html(job_id, payload)
        if action == "registry_html":
            return self._run_registry_html(job_id, payload)
        raise ValueError(f"Unsupported desktop action: {action}")

    def _run_collect(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        d = self._payload_date(payload)
        source_list = _parse_sources(payload.get("sources"))
        self._job_log(job_id, f"Collecting sources for {d.isoformat()}.")
        orch = self._make_orchestrator()
        results = asyncio.run(orch.collect(d, source_list))
        counts = {name: len(items) for name, items in results.items()}
        self._job_log(job_id, f"Collected {sum(counts.values())} items.")
        return {"date": d.isoformat(), "counts": counts}

    def _run_report(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        d = self._payload_date(payload)
        orch = self._make_orchestrator()
        if not orch.store.has_raw_data(d):
            self._job_log(job_id, "No raw data found; collecting first.")
            asyncio.run(orch.collect(d))
        self._job_log(job_id, "Generating overview report.")
        overview, _ = asyncio.run(orch.generate_overview(d))
        return {
            "date": d.isoformat(),
            "totalItems": overview.total_items,
            "overviewHtml": str(_resolve_against(self.project_root, orch.store.output_path(d, "daily_report.html"))),
            "reports": self._report_state(d),
        }

    def _run_pipeline(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        d = self._payload_date(payload)
        self._job_log(job_id, f"Running full pipeline for {d.isoformat()}.")
        orch = self._make_orchestrator()
        output_path = asyncio.run(orch.run(d))
        html_path = output_path.with_suffix(".html")
        return {
            "date": d.isoformat(),
            "overviewMarkdown": str(_resolve_against(self.project_root, output_path)),
            "overviewHtml": str(_resolve_against(self.project_root, html_path)),
            "reports": self._report_state(d),
        }

    def _run_deep_dive(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        d = self._payload_date(payload)
        selected = _merge_indices(payload.get("items"), payload.get("extraItems"))
        if not selected:
            raise ValueError("Choose at least one item index for deep dive.")

        orch = self._make_orchestrator()
        items_index = orch.store.load_json(orch.store.layer_relative_path("reports", d, "items_index.json"))
        if not items_index:
            raise ValueError("No items_index.json found. Generate the overview first.")

        self._job_log(job_id, f"Generating deep dive for items: {', '.join(f'{item:03d}' for item in selected)}.")
        report_model, _ = asyncio.run(orch.generate_deep_dive(d, selected))
        return {
            "date": d.isoformat(),
            "items": selected,
            "analysisCount": len(report_model.analyses),
            "deepDiveHtml": str(_resolve_against(self.project_root, orch.store.output_path(d, "deep_dive_report.html"))),
            "registryMonth": d.strftime("%Y-%m"),
            "reports": self._report_state(d),
        }

    def _run_html(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from src.reporters.html_renderer import (
            render_existing_data_report_html,
            render_existing_output_html,
        )

        d = self._payload_date(payload)
        self._job_log(job_id, f"Rendering existing HTML reports for {d.isoformat()}.")
        output_rendered = render_existing_output_html(self.project_root / "output", start_date=d, end_date=d)
        data_rendered = render_existing_data_report_html(self._data_dir(), start_date=d, end_date=d)
        rendered = output_rendered + data_rendered
        return {
            "date": d.isoformat(),
            "rendered": [str(_resolve_against(self.project_root, path)) for path in rendered],
            "reports": self._report_state(d),
        }

    def _run_registry_html(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        d = self._payload_date(payload)
        month = _parse_month(payload.get("month"), d)
        self._job_log(job_id, f"Rendering registry HTML for {month}.")
        store = self._make_registry_store()
        html_path = store.render_month_html(month)
        return {
            "month": month,
            "registryHtml": str(_resolve_against(self.project_root, html_path)),
        }

    # --- Factories and paths ---

    def _make_orchestrator(self) -> Any:
        if self._orchestrator_factory is not None:
            return self._orchestrator_factory()
        from src.cli import _get_orchestrator

        return _get_orchestrator()

    def _make_store(self) -> LocalStore:
        return LocalStore(os.environ.get("DATA_DIR", "data"))

    def _make_registry_store(self) -> RegistryStore:
        if self._registry_store_factory is not None:
            return self._registry_store_factory()
        return RegistryStore(self.project_root / "records")

    def _payload_date(self, payload: dict[str, Any]) -> date:
        return _parse_date(payload.get("date")) if payload.get("date") else self.default_date

    def _data_dir(self) -> Path:
        raw = Path(os.environ.get("DATA_DIR", "data"))
        return _resolve_against(self.project_root, raw)

    def _report_state(self, target_date: date) -> dict[str, Any]:
        overview_candidates = self._report_candidates("overview", target_date)
        deep_candidates = self._report_candidates("deep_dive", target_date)
        month = target_date.strftime("%Y-%m")
        registry_path = self._registry_dir() / f"{month}-record.html"
        return {
            "date": target_date.isoformat(),
            "overviewHtml": _first_existing_str(self.project_root, overview_candidates),
            "deepDiveHtml": _first_existing_str(self.project_root, deep_candidates),
            "registryHtml": str(registry_path) if registry_path.exists() else "",
            "hasOverview": any(path.exists() for path in overview_candidates),
            "hasDeepDive": any(path.exists() for path in deep_candidates),
            "hasRegistry": registry_path.exists(),
        }

    def _registry_dir(self) -> Path:
        return _resolve_against(self.project_root, self._make_registry_store().base_dir)

    def _report_candidates(self, kind: str, target_date: date) -> list[Path]:
        normalized = kind.strip().lower().replace("-", "_")
        if normalized not in _REPORT_KINDS:
            raise ValueError(f"Unsupported report kind: {kind}")
        output_name, data_name = _REPORT_KINDS[normalized]
        relative_date = LocalStore.relative_date_dir(target_date)
        return [
            self.project_root / "output" / relative_date / output_name,
            self._data_dir() / "reports" / relative_date / data_name,
        ]

    def _load_html_response(self, path: Path, *, date_label: str, kind: str) -> dict[str, Any]:
        resolved = self._read_allowed_html(path)
        return {
            "ok": True,
            "kind": kind,
            "date": date_label,
            "path": str(resolved),
            "html": resolved.read_text(encoding="utf-8"),
        }

    def _read_allowed_html(self, path: str | Path) -> Path:
        resolved = _resolve_against(self.project_root, Path(path))
        if resolved.suffix.lower() != ".html":
            raise PermissionError("Desktop shell can only load HTML files.")
        allowed_roots = [
            (self.project_root / "output").resolve(),
            (self._data_dir() / "reports").resolve(),
            self._registry_dir().resolve(),
        ]
        if not any(_is_relative_to(resolved, root) for root in allowed_roots):
            raise PermissionError(f"HTML path is outside allowed report directories: {resolved}")
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return resolved


def _parse_date(value: date | str | Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_month(value: Any, fallback_date: date) -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback_date.strftime("%Y-%m")
    date.fromisoformat(f"{raw}-01")
    return raw


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_sources(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        sources = [str(item).strip() for item in value if str(item).strip()]
    else:
        sources = [part.strip() for part in str(value).split(",") if part.strip()]
    return sources or None


def _merge_indices(items: Any, extra_items: Any = None) -> list[int]:
    values: list[int] = []

    def add(raw: Any) -> None:
        if raw is None:
            return
        if isinstance(raw, list):
            for item in raw:
                add(item)
            return
        for part in str(raw).replace("\uff0c", ",").split(","):
            stripped = part.strip().strip("[]")
            if not stripped:
                continue
            value = int(stripped)
            if value <= 0:
                raise ValueError(f"Item index must be positive: {value}")
            if value not in values:
                values.append(value)

    add(items)
    add(extra_items)
    return sorted(values)


def _parse_statuses(value: list[str] | str | None) -> list[InterestStatus]:
    if value is None:
        return []
    raw_values = value if isinstance(value, list) else str(value).split(",")
    parsed: list[InterestStatus] = []
    for raw in raw_values:
        token = str(raw).strip().lower()
        status = _STATUS_TOKEN_MAP.get(token)
        if status is None:
            raise ValueError(f"Unsupported status: {raw}")
        if status == InterestStatus.NONE:
            continue
        if status not in parsed:
            parsed.append(status)
    return [status for status in InterestStatus.ordered() if status in parsed]


def _resolve_against(project_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (project_root / path).resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _first_existing_str(project_root: Path, paths: list[Path]) -> str:
    for path in paths:
        if path.exists():
            return str(_resolve_against(project_root, path))
    return ""
