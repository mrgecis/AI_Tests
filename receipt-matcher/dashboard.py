"""
Receipt Matcher – Live Terminal Dashboard
==========================================
Displays real-time statistics and status of the receipt matching process.

Usage:
  python dashboard.py              # live auto-refresh every 5 s
  python dashboard.py --once       # print once and exit
  python dashboard.py --interval 10
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

import config

console = Console()

# ── CSV readers ───────────────────────────────────────────────────────────────
def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _read_all() -> dict:
    matched   = _read_csv(config.MATCHED_CSV)
    unmatched = _read_csv(config.UNMATCHED_CSV)
    requested = _read_csv(config.REQUESTED_CSV)

    # ChromaDB stats (optional – don't crash if index not built yet)
    index_docs = 0
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        _ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        col = client.get_or_create_collection(
            config.CHROMA_COLLECTION_NAME, embedding_function=_ef
        )
        index_docs = col.count()
    except Exception:
        pass

    return {
        "matched": matched,
        "unmatched": unmatched,
        "requested": requested,
        "index_docs": index_docs,
        "updated_at": datetime.now().strftime("%H:%M:%S"),
    }


# ── Widget builders ───────────────────────────────────────────────────────────
def _header() -> Panel:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return Panel(
        Text(f"  Receipt Matcher MVP  ·  {now}", style="bold cyan", justify="center"),
        style="cyan",
        padding=(0, 0),
    )


def _stats_panel(data: dict) -> Panel:
    matched   = len(data["matched"])
    unmatched = len(data["unmatched"])
    requested = len(data["requested"])
    total     = matched + unmatched
    rate      = matched / total if total else 0

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>5.1f}%"),
    )
    task = progress.add_task("Match rate", total=100, completed=int(rate * 100))

    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="right", style="bold")
    grid.add_column()
    grid.add_row("Indexed emails",  f"[green]{data['index_docs']}[/green]")
    grid.add_row("Transactions",    f"[white]{total}[/white]")
    grid.add_row("Matched",         f"[green]{matched}[/green]")
    grid.add_row("Unmatched",       f"[red]{unmatched}[/red]")
    grid.add_row("Requested",       f"[yellow]{requested}[/yellow]")
    grid.add_row("", "")
    grid.add_row("Match rate",      progress)

    return Panel(grid, title="[bold]Overview[/bold]", border_style="green", padding=(1, 2))


def _matched_table(data: dict) -> Panel:
    rows = data["matched"][-10:]  # last 10
    table = Table(box=box.SIMPLE_HEAD, expand=True, show_footer=False)
    table.add_column("Date",     style="dim",   width=11)
    table.add_column("Merchant", style="white", min_width=16)
    table.add_column("Amount",   justify="right", style="green", width=12)
    table.add_column("Confidence", justify="right", width=11)
    table.add_column("Matched receipt", style="dim", overflow="fold")

    for r in rows:
        conf = float(r.get("confidence", 0))
        conf_style = "green" if conf >= 0.8 else "yellow" if conf >= 0.65 else "red"
        table.add_row(
            r.get("date", "")[:10],
            r.get("merchant", "")[:30],
            f"{r.get('amount', '')} {r.get('currency', '')}",
            f"[{conf_style}]{conf:.0%}[/{conf_style}]",
            r.get("matched_subject", "")[:50],
        )

    title = f"[bold]Recently Matched[/bold]  [dim](last {len(rows)} of {len(data['matched'])})[/dim]"
    return Panel(table, title=title, border_style="green")


def _unmatched_table(data: dict) -> Panel:
    rows = data["unmatched"][-10:]
    table = Table(box=box.SIMPLE_HEAD, expand=True)
    table.add_column("Date",     style="dim",  width=11)
    table.add_column("Merchant", style="white", min_width=16)
    table.add_column("Amount",   justify="right", style="yellow", width=12)
    table.add_column("Reason",   style="dim",  overflow="fold")

    for r in rows:
        table.add_row(
            r.get("date", "")[:10],
            r.get("merchant", "")[:30],
            f"{r.get('amount', '')} {r.get('currency', '')}",
            r.get("reason", "")[:60],
        )

    title = f"[bold]Unmatched – manual review[/bold]  [dim](last {len(rows)} of {len(data['unmatched'])})[/dim]"
    return Panel(table, title=title, border_style="red")


def _footer(data: dict) -> Panel:
    paths = [
        f"[dim]matched.csv[/dim]   {config.MATCHED_CSV}",
        f"[dim]unmatched.csv[/dim] {config.UNMATCHED_CSV}",
        f"[dim]output/[/dim]       {config.OUTPUT_DIR}",
        f"[dim]Updated[/dim]       {data['updated_at']}",
    ]
    return Panel(
        "  ".join(paths),
        style="dim",
        padding=(0, 1),
    )


def _build_layout(data: dict) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(_header(),                        name="header",   size=3),
        Layout(name="body",                      ratio=1),
        Layout(_footer(data),                    name="footer",   size=3),
    )
    layout["body"].split_row(
        Layout(_stats_panel(data),               name="stats",    ratio=1),
        Layout(name="tables",                    ratio=3),
    )
    layout["tables"].split_column(
        Layout(_matched_table(data),             name="matched",  ratio=1),
        Layout(_unmatched_table(data),           name="unmatched",ratio=1),
    )
    return layout


# ── Entry point ───────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Receipt Matcher live dashboard")
    p.add_argument("--once",     action="store_true", help="Print once and exit")
    p.add_argument("--interval", type=float, default=5.0, metavar="SEC",
                   help="Refresh interval in seconds (default 5)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if args.once:
        data = _read_all()
        console.print(_build_layout(data))
        return

    try:
        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                data = _read_all()
                live.update(_build_layout(data))
                time.sleep(args.interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard closed.[/dim]")


if __name__ == "__main__":
    main()
