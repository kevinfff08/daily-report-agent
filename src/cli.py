"""CLI entry point for DailyReport using Typer."""

from __future__ import annotations

import asyncio
import os
from datetime import date

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.logging_config import get_logger, setup_logging
from src.models.registry import InterestStatus
from src.storage.registry_store import RegistryStore

load_dotenv()
setup_logging()

logger = get_logger("cli")
console = Console()
app = typer.Typer(
    name="dailyreport",
    help="Daily intelligence aggregation for AI/ML research.",
    no_args_is_help=True,
)
registry_app = typer.Typer(
    name="registry",
    help="维护 deep-dive 长期关注台账。",
)
app.add_typer(registry_app, name="registry")

_STATUS_OPTION_TO_SYMBOL = {
    "none": InterestStatus.NONE,
    "star": InterestStatus.STAR,
    "question": InterestStatus.QUESTION,
    "check": InterestStatus.CHECK,
}


def _parse_status_argument(value: str) -> list[InterestStatus]:
    """Parse one or more CLI status tokens."""
    parsed: list[InterestStatus] = []
    for raw in value.split(","):
        normalized = raw.strip().lower()
        if not normalized:
            continue
        if normalized not in _STATUS_OPTION_TO_SYMBOL:
            raise ValueError(f"Invalid status: {raw.strip()}")
        status = _STATUS_OPTION_TO_SYMBOL[normalized]
        if status == InterestStatus.NONE:
            return []
        if status not in parsed:
            parsed.append(status)
    return parsed


def _status_argument_requests_clear(value: str) -> bool:
    """Return whether the CLI argument explicitly asked to clear statuses."""
    return any(raw.strip().lower() == "none" for raw in value.split(","))


def _get_orchestrator() -> "DailyReportOrchestrator":
    """Create the orchestrator from environment config."""
    from src.orchestrator import DailyReportOrchestrator

    llm_provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    llm_mode = os.environ.get("LLM_MODE", "api-key")
    if llm_provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = None
    if llm_mode == "setup-token":
        base_url = os.environ.get("LLM_PROXY_URL", "http://localhost:8317")

    return DailyReportOrchestrator(
        data_dir=os.environ.get("DATA_DIR", "data"),
        config_dir=os.environ.get("CONFIG_DIR", "config"),
        llm_provider=llm_provider,
        api_key=api_key,
        llm_model=os.environ.get("LLM_MODEL"),
        base_url=base_url,
    )


def _parse_date(date_str: str | None) -> date:
    """Parse date string or return today."""
    if date_str:
        return date.fromisoformat(date_str)
    return date.today()


def _get_registry_store() -> RegistryStore:
    """Create the registry store."""
    return RegistryStore()


def _get_registry_manager() -> "DeepDiveRegistryManager":
    """Create the registry manager with the configured LLM."""
    return _get_orchestrator().registry_manager


@app.command()
def collect(
    target_date: str = typer.Option(None, "--date", "-d", help="Target date (YYYY-MM-DD), defaults to today"),
    sources: str = typer.Option(None, "--sources", "-s", help="Comma-separated sources: arxiv,hackernews,youtube,bilibili,semantic_scholar,github_trending,product_hunt,tavily"),
) -> None:
    """Collect data from configured sources."""
    d = _parse_date(target_date)
    source_list = [s.strip() for s in sources.split(",")] if sources else None

    console.print(Panel(f"[bold]Collecting data for {d}[/bold]", style="blue"))
    orch = _get_orchestrator()
    results = asyncio.run(orch.collect(d, source_list))

    table = Table(title="Collection Results")
    table.add_column("Source", style="cyan")
    table.add_column("Items", justify="right", style="green")
    for name, items in results.items():
        table.add_row(name, str(len(items)))
    console.print(table)

    total = sum(len(v) for v in results.values())
    console.print(f"\n[bold green]Total: {total} items collected[/bold green]")


@app.command()
def report(
    target_date: str = typer.Option(None, "--date", "-d", help="Target date (YYYY-MM-DD)"),
) -> None:
    """Generate Stage 1 overview report (collect if needed + 3 LLM calls)."""
    d = _parse_date(target_date)
    console.print(Panel(f"[bold]Generating overview report for {d}[/bold]", style="blue"))

    orch = _get_orchestrator()
    if not orch.store.has_raw_data(d):
        console.print("[yellow]No raw data found. Collecting first...[/yellow]")
        asyncio.run(orch.collect(d))

    overview, _ = asyncio.run(orch.generate_overview(d))
    console.print(f"\n[bold green]Report generated: {overview.total_items} items[/bold green]")
    console.print(f"Output: output/{d.isoformat()}/daily_report.md")


@app.command(name="deep-dive")
def deep_dive(
    items: str = typer.Option(..., "--items", "-i", help="Comma-separated item indices, e.g. '1,3,15'"),
    target_date: str = typer.Option(None, "--date", "-d", help="Target date (YYYY-MM-DD)"),
) -> None:
    """Generate Stage 2 deep dive report for selected items."""
    d = _parse_date(target_date)
    indices: list[int] = []
    for raw in items.split(","):
        value = raw.strip()
        try:
            indices.append(int(value))
        except ValueError:
            console.print(f"[red]Invalid index: {value}[/red]")
            raise typer.Exit(1)

    console.print(Panel(f"[bold]Deep dive for {d}: items {indices}[/bold]", style="blue"))

    orch = _get_orchestrator()
    items_index = orch.store.load_json(f"reports/{d.isoformat()}/items_index.json")
    if not items_index:
        console.print("[red]No items index found. Run 'report' first to generate the overview.[/red]")
        raise typer.Exit(1)

    report_model, _ = asyncio.run(orch.generate_deep_dive(d, indices))
    console.print(f"\n[bold green]Deep dive complete: {len(report_model.analyses)} analyses[/bold green]")
    console.print(f"Output: output/{d.isoformat()}/deep_dive_report.md")


@app.command()
def run(
    target_date: str = typer.Option(None, "--date", "-d", help="Target date (YYYY-MM-DD)"),
) -> None:
    """Execute full pipeline: collect + overview report."""
    d = _parse_date(target_date)
    console.print(Panel(f"[bold]Running full pipeline for {d}[/bold]", style="blue"))

    orch = _get_orchestrator()
    output_path = asyncio.run(orch.run(d))
    console.print("\n[bold green]Pipeline complete![/bold green]")
    console.print(f"Report: {output_path}")


@app.command()
def status() -> None:
    """Show system configuration and data status."""
    orch = _get_orchestrator()
    info = orch.get_status()

    console.print(Panel("[bold]DailyReport System Status[/bold]", style="blue"))

    config_table = Table(title="Configuration")
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="white")
    config_table.add_row("LLM Provider", info["llm_provider"])
    config_table.add_row("LLM Model", info["llm_model"])
    config_table.add_row("Collectors", ", ".join(info["collectors"]))
    config_table.add_row("arXiv Categories", ", ".join(info["config"]["arxiv_categories"]))
    config_table.add_row("HN Min Score", str(info["config"]["hn_min_score"]))
    config_table.add_row("YouTube Channels", str(info["config"]["youtube_channels"]))
    config_table.add_row("Bilibili Users", str(info["config"]["bilibili_users"]))
    config_table.add_row("S2 Topics", ", ".join(info["config"]["semantic_scholar_topics"]))
    config_table.add_row("GH Languages", ", ".join(info["config"]["github_trending_languages"]))
    config_table.add_row("PH Topics", ", ".join(info["config"]["product_hunt_topics"]))
    config_table.add_row("Tavily Searches", str(info["config"]["tavily_searches"]))
    console.print(config_table)

    data_table = Table(title="Available Data")
    data_table.add_column("Layer", style="cyan")
    data_table.add_column("Dates", style="white")
    data_table.add_row("Raw", ", ".join(info["data"]["raw_dates"]) or "(none)")
    data_table.add_row("Analyzed", ", ".join(info["data"]["analyzed_dates"]) or "(none)")
    data_table.add_row("Reports", ", ".join(info["data"]["report_dates"]) or "(none)")
    console.print(data_table)


@registry_app.command("show")
def registry_show(
    month: str = typer.Option(None, "--month", help="仅显示指定月份的记录 (YYYY-MM)"),
    status: str = typer.Option(None, "--status", "-s", help="过滤状态: star, question, check, none"),
    limit: int = typer.Option(50, "--limit", "-n", min=1, help="最多显示多少条记录"),
) -> None:
    """Show registry entries in a readable table."""
    store = _get_registry_store()
    entries = store.load_month_entries(month) if month else store.load_all_entries()

    if status:
        normalized = status.strip().lower()
        if normalized not in _STATUS_OPTION_TO_SYMBOL:
            console.print(f"[red]Invalid status: {status}[/red]")
            raise typer.Exit(1)
        wanted_status = _STATUS_OPTION_TO_SYMBOL[normalized]
        if wanted_status == InterestStatus.NONE:
            entries = [entry for entry in entries if not entry.interest_statuses]
        else:
            entries = [entry for entry in entries if entry.has_interest_status(wanted_status)]

    entries = entries[:limit]
    if not entries:
        console.print("[yellow]台账为空，或没有符合筛选条件的记录。[/yellow]")
        return

    table = Table(title="Deep Dive 长期关注台账")
    table.add_column("日期", style="cyan")
    table.add_column("记录ID", style="white")
    table.add_column("标题", style="green")
    table.add_column("关键词", style="magenta")
    table.add_column("属性", style="yellow")
    table.add_column("摘要", style="blue")
    table.add_column("状态", style="white")

    for entry in entries:
        table.add_row(
            entry.date.isoformat(),
            entry.record_id,
            entry.title,
            " / ".join(entry.keywords),
            entry.attribute.value,
            entry.summary_ref,
            entry.interest_status_display,
        )

    console.print(table)


@registry_app.command("mark")
def registry_mark(
    record_id: str = typer.Option(..., "--id", help="记录ID，例如 20260325-001"),
    status: str = typer.Option(..., "--status", "-s", help="目标状态: star, question, check, none；可用逗号传多个"),
    mode: str = typer.Option("add", "--mode", help="更新模式: add, set, remove, clear"),
) -> None:
    """Update the interest status for a registry item."""
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"add", "set", "remove", "clear"}:
        console.print(f"[red]Invalid mode: {mode}[/red]")
        raise typer.Exit(1)

    try:
        statuses = _parse_status_argument(status)
    except ValueError:
        console.print(f"[red]Invalid status: {status}[/red]")
        raise typer.Exit(1)

    requested_clear = _status_argument_requests_clear(status)
    if requested_clear and normalized_mode == "add":
        normalized_mode = "clear"

    if normalized_mode == "clear":
        statuses = []
    elif not statuses:
        console.print("[red]Status cannot be empty unless mode=clear or status=none[/red]")
        raise typer.Exit(1)

    store = _get_registry_store()
    try:
        entry = store.update_interest_statuses(record_id, statuses, mode=normalized_mode)
    except KeyError:
        console.print(f"[red]未找到记录 {record_id}[/red]")
        raise typer.Exit(1)

    display_status = entry.interest_status_display or "(空)"
    console.print(f"[bold green]已更新[/bold green] {record_id} -> {display_status}")


@registry_app.command("find")
def registry_find(
    query: str = typer.Option(..., "--query", "-q", help="用于匹配条目的查询文本"),
    limit: int = typer.Option(10, "--limit", "-n", min=1, help="最多返回多少条结果"),
) -> None:
    """Find related registry entries from all monthly records."""
    manager = _get_registry_manager()
    store = _get_registry_store()
    match_method, entries = manager.find_entries(query, limit)
    if not entries:
        console.print("[yellow]没有找到匹配条目。[/yellow]")
        return

    method_label = {
        "keywords": "关键词匹配",
        "summary": "摘要匹配",
        "llm": "LLM 回退匹配",
    }[match_method]
    console.print(Panel(f"[bold]{method_label}[/bold]", style="blue"))

    table = Table(title="匹配结果")
    table.add_column("文件名", style="cyan")
    table.add_column("日期", style="white")
    table.add_column("记录ID", style="green")
    table.add_column("标题", style="magenta")

    for entry in entries:
        file_name = store.resolve_month_path(entry.date).name
        table.add_row(file_name, entry.date.isoformat(), entry.record_id, entry.title)

    console.print(table)


if __name__ == "__main__":
    app()
