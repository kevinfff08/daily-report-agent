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

load_dotenv()
setup_logging()

logger = get_logger("cli")
console = Console()
app = typer.Typer(
    name="dailyreport",
    help="Daily intelligence aggregation for AI/ML research.",
    no_args_is_help=True,
)


def _get_orchestrator() -> "DailyReportOrchestrator":
    """Create the orchestrator from environment config."""
    from src.orchestrator import DailyReportOrchestrator

    llm_mode = os.environ.get("LLM_MODE", "api-key")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = None
    if llm_mode == "setup-token":
        base_url = os.environ.get("LLM_PROXY_URL", "http://localhost:8317")

    return DailyReportOrchestrator(
        data_dir=os.environ.get("DATA_DIR", "data"),
        config_dir=os.environ.get("CONFIG_DIR", "config"),
        api_key=api_key,
        llm_model=os.environ.get("LLM_MODEL"),
        base_url=base_url,
    )


def _parse_date(date_str: str | None) -> date:
    """Parse date string or return today."""
    if date_str:
        return date.fromisoformat(date_str)
    return date.today()


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

    # Check if we have raw data, if not collect first
    if not orch.store.has_raw_data(d):
        console.print("[yellow]No raw data found. Collecting first...[/yellow]")
        asyncio.run(orch.collect(d))

    overview, markdown = asyncio.run(orch.generate_overview(d))
    console.print(f"\n[bold green]Report generated: {overview.total_items} items[/bold green]")
    console.print(f"Output: output/{d.isoformat()}/daily_report.md")


@app.command(name="deep-dive")
def deep_dive(
    items: str = typer.Option(..., "--items", "-i", help="Comma-separated item indices, e.g. '1,3,15'"),
    target_date: str = typer.Option(None, "--date", "-d", help="Target date (YYYY-MM-DD)"),
) -> None:
    """Generate Stage 2 deep dive report for selected items."""
    d = _parse_date(target_date)

    # Parse indices
    indices = []
    for s in items.split(","):
        s = s.strip()
        try:
            indices.append(int(s))
        except ValueError:
            console.print(f"[red]Invalid index: {s}[/red]")
            raise typer.Exit(1)

    console.print(Panel(
        f"[bold]Deep dive for {d}: items {indices}[/bold]",
        style="blue",
    ))

    orch = _get_orchestrator()

    # Check for items_index (created by overview report)
    items_index = orch.store.load_json(
        f"reports/{d.isoformat()}/items_index.json"
    )
    if not items_index:
        console.print("[red]No items index found. Run 'report' first to generate the overview.[/red]")
        raise typer.Exit(1)

    report_model, markdown = asyncio.run(orch.generate_deep_dive(d, indices))
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
    console.print(f"\n[bold green]Pipeline complete![/bold green]")
    console.print(f"Report: {output_path}")


@app.command()
def status() -> None:
    """Show system configuration and data status."""
    orch = _get_orchestrator()
    info = orch.get_status()

    console.print(Panel("[bold]DailyReport System Status[/bold]", style="blue"))

    # Config
    config_table = Table(title="Configuration")
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="white")
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

    # Data
    data_table = Table(title="Available Data")
    data_table.add_column("Layer", style="cyan")
    data_table.add_column("Dates", style="white")
    data_table.add_row("Raw", ", ".join(info["data"]["raw_dates"]) or "(none)")
    data_table.add_row("Analyzed", ", ".join(info["data"]["analyzed_dates"]) or "(none)")
    data_table.add_row("Reports", ", ".join(info["data"]["report_dates"]) or "(none)")
    console.print(data_table)


if __name__ == "__main__":
    app()
