"""Typer CLI entry point. Commands per PLAN.md §11."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import db

app = typer.Typer(
    help="HTGF Early-Stage Sourcing Tool",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


# ---- global state ---------------------------------------------------------

# Populated by the root callback so subcommands can read them.
STATE: dict = {
    "config": None,
    "dry_run": False,
    "no_sheets": False,
    "max_spend": 20.0,
    "verbose": False,
}


@app.callback()
def main(
    config: Path = typer.Option(None, "--config", help="Path to a config YAML override."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan but don't write outputs."),
    no_sheets: bool = typer.Option(False, "--no-sheets", help="Skip Google Sheets export."),
    max_spend: float = typer.Option(
        20.0, "--max-spend", help="Abort if cumulative LLM cost (USD) exceeds this."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose logging."),
) -> None:
    """Global flags shared by all subcommands."""
    _load_dotenv_if_present()
    STATE["config"] = config
    STATE["dry_run"] = dry_run
    STATE["no_sheets"] = no_sheets
    STATE["max_spend"] = max_spend
    STATE["verbose"] = verbose

    # Honour --max-spend across all subsequent LLM calls.
    from . import llm

    llm.set_max_spend(max_spend)


# ---- subcommands ----------------------------------------------------------


def _stub(name: str) -> None:
    console.print(f"[yellow]{name}: not implemented yet[/yellow]")


def _safe_llm_run(thunk):
    """Run an LLM-using callable; emit a clean message on `BudgetExceeded`."""
    from .llm import BudgetExceeded

    try:
        return thunk()
    except BudgetExceeded as e:
        console.print(f"[red]Budget cap reached:[/red] {e}")
        raise typer.Exit(code=3) from e


COLLECTOR_REGISTRY: dict[str, tuple[str, str]] = {
    "hackernews":      (".sources.hackernews",      "HackerNewsCollector"),
    "exist":           (".sources.exist",           "ExistCollector"),
    "universities":    (".sources.universities",    "UniversityCollector"),
    "github":          (".sources.github",          "GithubCollector"),
    "producthunt":     (".sources.producthunt",     "ProductHuntCollector"),
    "betalist":        (".sources.betalist",        "BetaListCollector"),
    "handelsregister": (".sources.handelsregister", "HandelsregisterCollector"),
}


def _load_collector(name: str):
    import importlib

    module_path, class_name = COLLECTOR_REGISTRY[name]
    module = importlib.import_module(module_path, package="htgf_sourcer")
    return getattr(module, class_name)


def _enabled_sources(config_path: Path = Path("config/sources.yaml")) -> list[str]:
    if not config_path.exists():
        return [n for n in COLLECTOR_REGISTRY if n != "handelsregister"]
    import yaml

    data = yaml.safe_load(config_path.read_text()) or {}
    sources = data.get("sources") or {}
    return [
        name
        for name, settings in sources.items()
        if isinstance(settings, dict)
        and settings.get("enabled")
        and name in COLLECTOR_REGISTRY
    ]


@app.command()
def discover(
    source: str = typer.Option(None, "--source", help="Run a single collector by name."),
    limit: int = typer.Option(
        None, "--limit", help="Cap leads returned per source (dev only)."
    ),
) -> None:
    """Run enabled collectors and persist new RawLead rows."""
    if source is not None and source not in COLLECTOR_REGISTRY:
        known = ", ".join(sorted(COLLECTOR_REGISTRY))
        console.print(f"[red]Unknown source: {source!r}. Known: {known}.[/red]")
        raise typer.Exit(code=2)

    names = [source] if source else _enabled_sources()
    if not names:
        console.print("[yellow]No sources enabled in config/sources.yaml.[/yellow]")
        return

    from .llm import BudgetExceeded

    grand_total = 0
    for name in names:
        try:
            collector_cls = _load_collector(name)
            collector = collector_cls()
            leads = asyncio.run(collector.collect(limit=limit))
        except BudgetExceeded as e:
            console.print(f"[red]Budget cap reached during {name}:[/red] {e}")
            raise typer.Exit(code=3) from e
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]{name}: failed — {e}[/red]")
            continue

        persisted = 0
        with db.connect() as conn:
            for lead in leads:
                lead_id = _lead_id(lead.source.value, lead.source_id)
                try:
                    db.upsert_lead(conn, lead_id, lead)
                    persisted += 1
                except Exception as e:  # noqa: BLE001
                    console.print(
                        f"[red]{name}: failed to persist {lead.source_id}: {e}[/red]"
                    )
        grand_total += persisted
        console.print(
            f"[green]{name}: collected {len(leads)}, persisted {persisted}.[/green]"
        )

    if len(names) > 1:
        console.print(f"[bold green]Total persisted: {grand_total}[/bold green]")


@app.command()
def enrich(
    limit: int = typer.Option(None, "--limit", help="Cap leads to enrich (dev only)."),
) -> None:
    """Fetch + LLM-extract pending leads into EnrichedStartup rows."""
    from .enrich import enrich_pending

    succeeded, failed = _safe_llm_run(
        lambda: asyncio.run(enrich_pending(limit=limit))
    )
    console.print(f"[green]enriched: {succeeded}, failed: {failed}.[/green]")


@app.command()
def score(
    limit: int = typer.Option(None, "--limit", help="Cap startups to score (dev only)."),
) -> None:
    """Score all enriched startups against the HTGF thesis."""
    from .score import score_all

    succeeded, failed = _safe_llm_run(lambda: score_all(limit=limit))
    console.print(f"[green]scored: {succeeded}, failed: {failed}.[/green]")


@app.command()
def dedup(
    limit: int = typer.Option(None, "--limit", help="Cap websiteless leads checked."),
) -> None:
    """Pairwise-match websiteless leads against enriched startups (Haiku)."""
    from .dedup import pairwise_match_leads

    n_checked, n_merged = _safe_llm_run(lambda: pairwise_match_leads(limit=limit))
    console.print(
        f"[green]dedup: checked {n_checked} pair(s), merged {n_merged} lead(s).[/green]"
    )


@app.command()
def export(
    top_n: int = typer.Option(
        None, "--top-n", help="Cap how many one-pagers to write (default: all scored)."
    ),
) -> None:
    """Write CSV, XLSX, one-pagers, and (optionally) push to Google Sheets."""
    from .export import export_all

    result = export_all(top_n_onepagers=top_n, no_sheets=STATE["no_sheets"])
    table = Table(title="Export")
    table.add_column("Artifact", style="cyan")
    table.add_column("Detail")
    table.add_row("CSV", str(result["csv"]))
    table.add_row("XLSX", str(result["xlsx"]))
    table.add_row("Run summary", str(result["run_summary"]))
    table.add_row(
        "One-pagers",
        f"{result['onepagers_written']} written (of {result['total_scored']} scored)",
    )
    table.add_row("Google Sheets", str(result["sheets"]))
    console.print(table)


@app.command(name="run-all")
def run_all(
    discover_limit: int = typer.Option(
        None, "--discover-limit", help="Cap leads per source during discover."
    ),
    enrich_limit: int = typer.Option(
        None, "--enrich-limit", help="Cap leads enriched."
    ),
    score_limit: int = typer.Option(
        None, "--score-limit", help="Cap startups scored."
    ),
    skip_dedup: bool = typer.Option(False, "--skip-dedup", help="Skip Stage-2 Haiku dedup."),
) -> None:
    """Discover → enrich → dedup → score → export, in sequence."""
    console.print("[bold]1/5 discover[/bold]")
    discover(source=None, limit=discover_limit)

    console.print("\n[bold]2/5 enrich[/bold]")
    enrich(limit=enrich_limit)

    if not skip_dedup:
        console.print("\n[bold]3/5 dedup[/bold]")
        dedup(limit=None)
    else:
        console.print("\n[bold]3/5 dedup[/bold] [yellow](skipped)[/yellow]")

    console.print("\n[bold]4/5 score[/bold]")
    score(limit=score_limit)

    console.print("\n[bold]5/5 export[/bold]")
    export(top_n=None)


@app.command()
def status() -> None:
    """Show counts and cost-to-date."""
    with db.connect() as conn:
        c = db.counts(conn)
        cost = db.total_llm_cost(conn)
    table = Table(title="HTGF Sourcer Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    for k, v in c.items():
        table.add_row(k, str(v))
    table.add_row("llm_cost_usd", f"${cost:.4f}")
    console.print(table)


@app.command()
def doctor() -> None:
    """Verify env vars, tool availability, and cache health."""
    table = Table(title="HTGF Sourcer Doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")

    fails = 0

    # Python version
    if sys.version_info >= (3, 11):
        table.add_row(
            "Python ≥ 3.11",
            "[green]PASS[/]",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    else:
        table.add_row("Python ≥ 3.11", "[red]FAIL[/]", sys.version.split()[0])
        fails += 1

    # Required env
    if os.environ.get("ANTHROPIC_API_KEY"):
        table.add_row("ANTHROPIC_API_KEY", "[green]PASS[/]", "set")
    else:
        table.add_row("ANTHROPIC_API_KEY", "[red]FAIL[/]", "missing (required)")
        fails += 1

    # Recommended env
    for var in ("GITHUB_TOKEN", "PRODUCT_HUNT_TOKEN", "FIRECRAWL_API_KEY"):
        if os.environ.get(var):
            table.add_row(var, "[green]PASS[/]", "set")
        else:
            table.add_row(var, "[yellow]WARN[/]", "missing (recommended)")

    # Optional env (Google Sheets)
    sa_path = os.environ.get("GOOGLE_SA_PATH")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if sa_path and sheet_id:
        if Path(sa_path).expanduser().exists():
            table.add_row("Google Sheets", "[green]PASS[/]", "service account + sheet ID set")
        else:
            table.add_row(
                "Google Sheets",
                "[yellow]WARN[/]",
                f"GOOGLE_SA_PATH points to missing file: {sa_path}",
            )
    else:
        table.add_row("Google Sheets", "[blue]INFO[/]", "optional (use --no-sheets to skip)")

    # Playwright
    status_, detail = _check_playwright()
    color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}[status_]
    table.add_row("Playwright (chromium)", f"[{color}]{status_}[/]", detail)
    if status_ == "FAIL":
        fails += 1

    # Cache dir writable
    cache_dir = Path("cache")
    try:
        cache_dir.mkdir(exist_ok=True)
        test_file = cache_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        table.add_row("cache/ writable", "[green]PASS[/]", str(cache_dir.resolve()))
    except Exception as e:  # noqa: BLE001
        table.add_row("cache/ writable", "[red]FAIL[/]", str(e))
        fails += 1

    # SQLite init
    try:
        path = db.init_db()
        table.add_row("SQLite state.db", "[green]PASS[/]", str(path.resolve()))
    except Exception as e:  # noqa: BLE001
        table.add_row("SQLite state.db", "[red]FAIL[/]", str(e))
        fails += 1

    console.print(table)
    if fails:
        console.print(f"\n[red]{fails} check(s) failed.[/red]")
        raise typer.Exit(code=1)
    console.print("\n[green]All required checks passed.[/green]")


# ---- helpers --------------------------------------------------------------


def _load_dotenv_if_present(path: Path = Path(".env")) -> None:
    """Minimal .env loader. Runs before every command via the root callback."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _lead_id(source: str, source_id: str) -> str:
    return hashlib.sha256(f"{source}:{source_id}".encode()).hexdigest()


def _check_playwright() -> tuple[str, str]:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return "FAIL", "playwright package not installed (run `uv sync`)"

    candidate_caches = [
        Path.home() / "Library" / "Caches" / "ms-playwright",  # macOS
        Path.home() / ".cache" / "ms-playwright",  # Linux
    ]
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        candidate_caches.insert(0, Path(env_path))

    for cache in candidate_caches:
        if cache.exists() and any(cache.glob("chromium-*")):
            return "PASS", f"chromium installed at {cache}"
    return "WARN", "chromium not installed — run: uv run playwright install chromium"


if __name__ == "__main__":
    app()
