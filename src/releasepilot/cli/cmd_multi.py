"""CLI ``multi`` command - generate release notes from multiple repositories."""

from __future__ import annotations

import os
from pathlib import Path

import click

from releasepilot.cli.app import cli
from releasepilot.cli.errors import UserError
from releasepilot.cli.helpers import (
    _ALL_AUDIENCES,
    _atomic_write_text,
    _build_settings,
    console,
)
from releasepilot.pipeline import orchestrator
from releasepilot.pipeline.orchestrator import PipelineError
from releasepilot.sources.git import GitCollectionError
from releasepilot.sources.structured import StructuredFileError


@cli.command()
@click.argument("repos", nargs=-1, required=True)
@click.option(
    "--audience",
    type=click.Choice(_ALL_AUDIENCES),
    default="changelog",
    help="Target audience",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "plaintext", "json"]),
    default="markdown",
    help="Output format",
)
@click.option("--since", "since_date", default="", help="Commits since date (YYYY-MM-DD)")
@click.option("--branch", default="", help="Branch to analyze")
@click.option("--language", "lang", default="en", help="Output language")
@click.option("--show-authors", is_flag=True, help="Include author names")
@click.option("-o", "--output-dir", default="", help="Directory for per-repo output files")
def multi(
    repos: tuple[str, ...],
    audience: str,
    output_format: str,
    since_date: str,
    branch: str,
    lang: str,
    show_authors: bool,
    output_dir: str,
):
    """Generate release notes from multiple repositories at once.

    Pass one or more repository paths as arguments. Each repository is
    processed independently and results are output as clearly separated sections.

    Examples:

        releasepilot multi ./repo1 ./repo2 ./repo3

        releasepilot multi ./repo1 ./repo2 --since 2025-01-01 -o ./output/
    """
    # Validate output directory early if specified.
    if output_dir:
        out_dir = Path(output_dir)
        if out_dir.exists() and not os.access(out_dir, os.W_OK):
            UserError(
                summary=f"Output directory not writable: '{output_dir}'",
                reason="No write permission for the specified output directory.",
                suggestions=["Check directory permissions or use a different path"],
            ).exit()

    combined_parts: list[str] = []
    is_executive = audience == "executive"
    is_narrative = audience in ("narrative", "customer-narrative")
    failed_repos: list[str] = []
    skipped_repos: list[str] = []

    for repo_path in repos:
        repo_label = Path(repo_path).resolve().name
        console.print(f"\n[bold cyan]Processing:[/bold cyan] {repo_label} ({repo_path})")

        settings = _build_settings(
            repo=repo_path,
            from_ref="",
            to_ref="HEAD",
            source_file="",
            version_str="",
            title="",
            branch=branch,
            since_date=since_date,
            audience=audience,
            output_format=output_format,
            show_authors=show_authors,
            lang=lang,
        )

        try:
            with console.status(f"[bold cyan]Analyzing {repo_label}...[/bold cyan]"):
                if is_executive:
                    from releasepilot.cli.cmd_generate import _build_executive_brief

                    brief = _build_executive_brief(settings)
                    from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer

                    if output_format == "json":
                        output = ExecutiveMarkdownRenderer().render_json(brief)
                    else:
                        output = ExecutiveMarkdownRenderer().render(brief, lang=lang)
                elif is_narrative:
                    from releasepilot.cli.cmd_generate import _build_narrative_brief

                    brief = _build_narrative_brief(settings)
                    from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer

                    if output_format == "json":
                        output = NarrativeMarkdownRenderer().render_json(brief)
                    else:
                        output = NarrativeMarkdownRenderer().render(brief, lang=lang)
                else:
                    output = orchestrator.generate(settings)
        except (PipelineError, GitCollectionError, StructuredFileError) as exc:
            console.print(f"  [red]✗ Error:[/red] {exc}")
            failed_repos.append(repo_label)
            continue

        if not output.strip():
            console.print(f"  [yellow]⚠ No changes found for {repo_label}[/yellow]")
            skipped_repos.append(repo_label)
            continue

        console.print("  [green]✓[/green] Done")

        if output_dir:
            ext = {
                "markdown": ".md",
                "plaintext": ".txt",
                "json": ".json",
            }[output_format]
            out_path = Path(output_dir) / f"{repo_label}{ext}"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(str(out_path), output)
            console.print(f"  [green]✓[/green] Saved to {out_path}")
        else:
            combined_parts.append(output)

    if not output_dir and combined_parts:
        click.echo("\n".join(combined_parts))

    # Print failure summary and exit non-zero if any repos failed
    total = len(repos)
    success = total - len(failed_repos) - len(skipped_repos)
    if failed_repos or skipped_repos:
        console.print()
        console.print(f"[bold]Summary:[/bold] {success}/{total} succeeded", highlight=False)
        if failed_repos:
            console.print(f"  [red]Failed ({len(failed_repos)}):[/red] {', '.join(failed_repos)}")
        if skipped_repos:
            console.print(
                f"  [yellow]Skipped - no changes ({len(skipped_repos)}):[/yellow] {', '.join(skipped_repos)}"
            )
    if failed_repos:
        raise SystemExit(1)
