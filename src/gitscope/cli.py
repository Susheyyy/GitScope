from __future__ import annotations

from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table

from gitscope.analyzer import AnalysisEngine
from gitscope.exporter import Exporter
from gitscope.git_manager import GitRepoManager
from gitscope.parser import GitLogParser

console = Console()


@click.group()
def main():
    pass


@main.command()
@click.argument("target", type=str)
@click.option("--since", type=str, default=None, help="Filter commits after date (e.g. '30 days ago', '2024-01-01')")
@click.option("--until", type=str, default=None, help="Filter commits up to date")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "markdown", "json"], case_sensitive=False),
    default="terminal",
)
@click.option("--output", type=click.Path(writable=True), default=None, help="Save report to file path")
def analyze(target: str, since: Optional[str], until: Optional[str], output_format: str, output: Optional[str]):
    try:
        with console.status(f"[bold cyan]Preparing repository {target}...[/bold cyan]"):
            manager = GitRepoManager(target)
            repo_path = manager.prepare()
            repo_name = Path(repo_path).name

        with console.status("[bold cyan]Extracting and parsing commit history...[/bold cyan]"):
            parser = GitLogParser(repo_path, since=since, until=until)
            commits = list(parser.parse_commits())

        with console.status("[bold cyan]Analyzing hotspots and ownership metrics...[/bold cyan]"):
            engine = AnalysisEngine(repo_name=repo_name, repo_path=str(repo_path), since=since, until=until)
            report = engine.analyze(commits)

        if output_format == "json":
            result = Exporter.to_json(report)
            if output:
                Path(output).write_text(result, encoding="utf-8")
                console.print(f"[green]Report saved to {output}[/green]")
            else:
                click.echo(result)
            return

        if output_format == "markdown":
            result = Exporter.to_markdown(report)
            if output:
                Path(output).write_text(result, encoding="utf-8")
                console.print(f"[green]Report saved to {output}[/green]")
            else:
                click.echo(result)
            return

        _render_terminal_dashboard(report)

        if output:
            Path(output).write_text(Exporter.to_markdown(report), encoding="utf-8")
            console.print(f"\n[green]Markdown copy of report saved to {output}[/green]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise click.Abort()


def _render_terminal_dashboard(report):
    console.print(f"\n[bold green]GitScope Analysis Report:[/bold green] [bold white]{report.repo_name}[/bold white]")
    console.print(f"Total Commits: [cyan]{report.total_commits}[/cyan] | Authors: [cyan]{report.total_authors}[/cyan]\n")

    f_table = Table(title="Top File Hotspots (High Churn & Bus-Factor Risk)")
    f_table.add_column("File Path", style="cyan", no_wrap=True)
    f_table.add_column("Commits", justify="right")
    f_table.add_column("Lines (+ / -)", justify="right")
    f_table.add_column("Bus Factor", justify="center")
    f_table.add_column("Risk", justify="center")
    f_table.add_column("Top Author", style="magenta")

    for f in report.hotspots_files[:10]:
        top_author = f.top_contributors[0].name if f.top_contributors else "N/A"
        risk_style = "bold red" if f.risk_level == "High" else ("yellow" if f.risk_level == "Medium" else "green")
        f_table.add_row(
            f.path,
            str(f.commits),
            f"+{f.lines_added} / -{f.lines_deleted}",
            str(f.bus_factor),
            f"[{risk_style}]{f.risk_level}[/{risk_style}]",
            top_author,
        )

    console.print(f_table)

    d_table = Table(title="\nDirectory Ownership Breakdown")
    d_table.add_column("Directory", style="cyan")
    d_table.add_column("Commits", justify="right")
    d_table.add_column("Total Churn", justify="right")
    d_table.add_column("Bus Factor", justify="center")
    d_table.add_column("Key Contributors", style="magenta")

    for d in report.hotspots_directories[:10]:
        authors_str = ", ".join([f"{c.name} ({int(c.ownership_percentage * 100)}%)" for c in d.top_contributors[:2]])
        d_table.add_row(
            d.path,
            str(d.commits),
            str(d.total_churn),
            str(d.bus_factor),
            authors_str,
        )

    console.print(d_table)


if __name__ == "__main__":
    main()
