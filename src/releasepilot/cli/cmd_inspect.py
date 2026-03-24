"""CLI inspection commands — ``preview``, ``collect``, ``analyze``."""

from __future__ import annotations

import click
from rich.panel import Panel
from rich.text import Text

from releasepilot.cli.app import cli
from releasepilot.cli.errors import empty_range
from releasepilot.cli.helpers import (
    _ALL_AUDIENCES,
    _build_settings,
    _common_options,
    _handle_error,
    _run_pipeline,
    console,
)
from releasepilot.cli.validators import validate_settings
from releasepilot.pipeline import orchestrator
from releasepilot.pipeline.orchestrator import PipelineError
from releasepilot.sources.git import GitCollectionError
from releasepilot.sources.structured import StructuredFileError

# ── preview ──────────────────────────────────────────────────────────────────


@cli.command()
@_common_options
@click.option(
    "--audience",
    type=click.Choice(_ALL_AUDIENCES),
    default="changelog",
    help="Target audience",
)
def preview(
    repo: str,
    from_ref: str,
    to_ref: str,
    source_file: str,
    version_str: str,
    title: str,
    app_name: str,
    lang: str,
    branch: str,
    since_date: str,
    dry_run: bool,
    audience: str,
):
    """Preview release notes in the terminal."""
    settings = _build_settings(
        repo,
        from_ref,
        to_ref,
        source_file,
        version_str,
        title,
        branch,
        since_date,
        audience,
        output_format="plaintext",
        app_name=app_name,
        lang=lang,
    )

    # Executive preview uses the executive markdown renderer
    if audience == "executive":
        err = validate_settings(settings)
        if err:
            err.exit()
        try:
            from releasepilot.cli.cmd_generate import _build_executive_brief

            brief = _build_executive_brief(settings)
        except (PipelineError, GitCollectionError, StructuredFileError) as exc:
            _handle_error(exc)
            return
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer

        output = ExecutiveMarkdownRenderer().render(brief)
    elif audience in ("narrative", "customer-narrative"):
        err = validate_settings(settings)
        if err:
            err.exit()
        try:
            from releasepilot.cli.cmd_generate import _build_narrative_brief

            brief = _build_narrative_brief(settings)
        except (PipelineError, GitCollectionError, StructuredFileError) as exc:
            _handle_error(exc)
            return
        from releasepilot.rendering.narrative_plain import NarrativePlaintextRenderer

        output = NarrativePlaintextRenderer().render(brief)
    else:
        output = _run_pipeline(settings, dry_run=dry_run)

    if output:
        panel = Panel(
            Text(output),
            title="[bold]Release Notes Preview[/bold]",
            border_style="blue",
        )
        console.print(panel)


# ── collect ──────────────────────────────────────────────────────────────────


@cli.command()
@_common_options
def collect(
    repo: str,
    from_ref: str,
    to_ref: str,
    source_file: str,
    version_str: str,
    title: str,
    app_name: str,
    lang: str,
    branch: str,
    since_date: str,
    dry_run: bool,
):
    """Inspect collected change data before processing."""
    settings = _build_settings(
        repo,
        from_ref,
        to_ref,
        source_file,
        version_str,
        title,
        branch,
        since_date,
        app_name=app_name,
        lang=lang,
    )

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        release_range = orchestrator.build_release_range(settings)
        items = orchestrator.collect(settings, release_range)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    if not items:
        empty_range(release_range.from_ref, release_range.to_ref).display()
        return

    console.print(f"[bold]Collected {len(items)} changes[/bold]")
    console.print(f"Range: {release_range.from_ref}..{release_range.to_ref}\n")

    for item in items:
        scope = f" [{item.scope}]" if item.scope else ""
        console.print(f"  • {item.title}{scope}")
        if item.source.short_hash:
            console.print(f"    {item.source.short_hash} by {', '.join(item.authors)}")


# ── analyze ──────────────────────────────────────────────────────────────────


@cli.command()
@_common_options
def analyze(
    repo: str,
    from_ref: str,
    to_ref: str,
    source_file: str,
    version_str: str,
    title: str,
    app_name: str,
    lang: str,
    branch: str,
    since_date: str,
    dry_run: bool,
):
    """Show classification and grouping analysis."""
    settings = _build_settings(
        repo,
        from_ref,
        to_ref,
        source_file,
        version_str,
        title,
        branch,
        since_date,
        app_name=app_name,
        lang=lang,
    )

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        release_range = orchestrator.build_release_range(settings)
        raw_items = orchestrator.collect(settings, release_range)
        processed_items, stats = orchestrator.process_with_stats(settings, raw_items)
        notes = orchestrator.compose(settings, processed_items, release_range, stats)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    console.print("[bold]Release Analysis[/bold]")
    console.print(f"Range: {release_range.from_ref}..{release_range.to_ref}")
    console.print(f"Raw changes: {stats.raw}")
    console.print(f"After filter: {stats.after_filter}")
    console.print(f"After dedup: {stats.after_dedup}")
    console.print(f"Filtered out: {stats.filtered_out}")
    console.print(f"Dedup removed: {stats.dedup_removed}\n")

    for group in notes.groups:
        console.print(f"  {group.display_label}: {len(group.items)} items")

    if notes.breaking_changes:
        console.print(f"\n  [bold red]Breaking changes: {len(notes.breaking_changes)}[/bold red]")
