from __future__ import annotations

from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table

from analyzer import AnalysisEngine
from exporter import Exporter
from git_manager import GitRepoManager
from parser import GitLogParser

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
            existing_files = manager.get_existing_files()

        with console.status("[bold cyan]Analyzing git history (streaming)...[/bold cyan]"):
            parser = GitLogParser(repo_path, since=since, until=until)
            commit_stream = parser.parse_commits()
            engine = AnalysisEngine(
                repo_name=repo_name,
                repo_path=str(repo_path),
                since=since,
                until=until,
                existing_files=existing_files,
            )
            report = engine.analyze(commit_stream)

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
    console.print(f"Total Commits: [cyan]{report.total_commits}[/cyan] | Contributors: [cyan]{report.total_authors}[/cyan]\n")

    c_table = Table(title="👥 Contributor Breakdown (Who Contributed What)")
    c_table.add_column("Contributor", style="magenta", no_wrap=True)
    c_table.add_column("Commits", justify="right")
    c_table.add_column("Lines (+ / -)", justify="right")
    c_table.add_column("Total Churn", justify="right")
    c_table.add_column("Primary Focus Areas (Directories)", style="cyan")

    for c in report.contributors:
        areas = ", ".join(c.primary_directories) if c.primary_directories else "root"
        c_table.add_row(
            f"{c.name}\n[dim]{c.email}[/dim]",
            str(c.total_commits),
            f"+{c.lines_added} / -{c.lines_deleted}",
            str(c.total_churn),
            areas,
        )

    console.print(c_table)

    f_table = Table(title="\n📈 Top File Hotspots (High Churn & Bus-Factor Risk)")
    f_table.add_column("File Path", style="cyan", no_wrap=True)
    f_table.add_column("Status", justify="center")
    f_table.add_column("Commits", justify="right")
    f_table.add_column("Lines (+ / -)", justify="right")
    f_table.add_column("Bus Factor", justify="center")
    f_table.add_column("Risk", justify="center")
    f_table.add_column("Top Author", style="magenta")

    for f in report.hotspots_files[:10]:
        top_author = f.top_contributors[0].name if f.top_contributors else "N/A"
        risk_style = "bold red" if f.risk_level == "High" else ("yellow" if f.risk_level == "Medium" else "green")
        status_text = "[red]Deleted[/red]" if f.is_deleted else "[green]Active[/green]"
        f_table.add_row(
            f.path,
            status_text,
            str(f.commits),
            f"+{f.lines_added} / -{f.lines_deleted}",
            str(f.bus_factor),
            f"[{risk_style}]{f.risk_level}[/{risk_style}]",
            top_author,
        )

    console.print(f_table)

    d_table = Table(title="\n📂 Directory Ownership Breakdown")
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
