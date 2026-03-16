"""ReleasePilot CLI.

Commands:
  generate  — Generate release notes (full pipeline)
  preview   — Preview release notes in terminal
  collect   — Inspect collected change data
  analyze   — Show classification and grouping analysis
  export    — Write release notes to file
  guide     — Interactive guided workflow for QA/testers
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from releasepilot import __version__
from releasepilot.cli.errors import UserError, empty_range, git_command_failed
from releasepilot.cli.validators import (
    validate_export_format_deps,
    validate_export_path,
    validate_settings,
)
from releasepilot.config.settings import RenderConfig, Settings
from releasepilot.domain.enums import Audience, OutputFormat
from releasepilot.pipeline import orchestrator
from releasepilot.pipeline.orchestrator import PipelineError
from releasepilot.sources.git import GitCollectionError
from releasepilot.sources.structured import StructuredFileError

logger = logging.getLogger("releasepilot")

console = Console(stderr=True)

_ALL_FORMATS = ["markdown", "plaintext", "json", "pdf", "docx"]
_ALL_AUDIENCES = ["technical", "user", "summary", "changelog", "customer", "executive", "narrative", "customer-narrative"]


# ── Signal handling ─────────────────────────────────────────────────────────


def _install_signal_handlers() -> None:
    """Install graceful signal handlers so Ctrl-C exits cleanly."""
    def _handler(signum: int, _frame: object) -> None:
        sig_name = signal.Signals(signum).name
        console.print(f"\n[yellow]Interrupted ({sig_name}). Exiting.[/yellow]")
        raise SystemExit(128 + signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(OSError, ValueError):
            signal.signal(sig, _handler)


# ── Atomic write helpers ────────────────────────────────────────────────────


def _atomic_write_text(path: str, content: str) -> None:
    """Write *content* to *path* atomically (write-to-temp then rename)."""
    target = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, target)
    except BaseException:
        with _SuppressOs():
            os.close(fd)
        with _SuppressOs():
            os.unlink(tmp)
        raise


def _atomic_write_bytes(path: str, data: bytes) -> None:
    """Write *data* to *path* atomically."""
    target = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp, target)
    except BaseException:
        with _SuppressOs():
            os.close(fd)
        with _SuppressOs():
            os.unlink(tmp)
        raise


class _SuppressOs:
    """Tiny context manager that suppresses OSError."""
    def __enter__(self): return self
    def __exit__(self, *a): return isinstance(a[1], OSError)


def _make_cli_progress():
    """Return a progress callback that logs to stderr when running interactively."""
    if not console.is_terminal:
        from releasepilot.pipeline.progress import noop_progress
        return noop_progress

    def _cb(stage: str, detail: str = "", current: int = 0, total: int = 0) -> None:
        msg = f"  [dim]⟳ {stage}[/dim]"
        if detail:
            msg += f" [dim]— {detail}[/dim]"
        console.print(msg, highlight=False)

    return _cb


# ── Shared CLI options ──────────────────────────────────────────────────────


def _common_options(fn):
    """Decorator that adds shared options to all commands."""
    fn = click.option("--repo", default=".", help="Path to git repository")(fn)
    fn = click.option("--from", "from_ref", default="", help="Start ref (tag/commit/branch)")(fn)
    fn = click.option("--to", "to_ref", default="HEAD", help="End ref (default: HEAD)")(fn)
    fn = click.option("--source-file", default="", help="JSON file with structured changes")(fn)
    fn = click.option("--version", "version_str", default="", help="Release version label")(fn)
    fn = click.option("--title", default="", help="Custom title phrase")(fn)
    fn = click.option("--app-name", default="", help="Application/product name (e.g. Loudly)")(fn)
    fn = click.option(
        "--language", "lang", default=None,
        help="Output language (en, pl, de, fr, es, it, pt, nl, uk, cs)",
    )(fn)
    fn = click.option("--branch", default="", help="Branch to analyze (for date-range mode)")(fn)
    fn = click.option(
        "--since", "since_date", default="",
        help="Collect commits since date (YYYY-MM-DD)",
    )(fn)
    fn = click.option("--dry-run", is_flag=True, help="Show pipeline summary without rendering")(fn)
    return fn


def _build_settings(
    repo: str,
    from_ref: str,
    to_ref: str,
    source_file: str,
    version_str: str,
    title: str,
    branch: str = "",
    since_date: str = "",
    audience: str | None = None,
    output_format: str | None = None,
    output_file: str = "",
    show_authors: bool = False,
    show_hashes: bool = False,
    app_name: str = "",
    lang: str | None = None,
) -> Settings:
    # Load config file defaults (CLI values override)
    from releasepilot.config.file_config import load_config

    cfg = load_config(repo)
    if cfg.warnings:
        for w in cfg.warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]", highlight=False)
    app_name = app_name or cfg.app_name
    # Use CLI value if explicitly provided, else config, else hardcoded default.
    lang = lang if lang is not None else (cfg.language or "en")
    audience = audience if audience is not None else (cfg.audience or "changelog")
    output_format = output_format if output_format is not None else (cfg.format or "markdown")
    branch = branch or cfg.branch
    title = title or cfg.title
    version_str = version_str or cfg.version
    show_authors = show_authors or cfg.show_authors
    show_hashes = show_hashes or cfg.show_hashes
    accent_color = cfg.accent_color or "#FB6400"

    # Map pdf/docx to markdown internally (renderers handle the real output)
    internal_format = output_format if output_format in ("markdown", "plaintext", "json") else "markdown"
    return Settings(
        repo_path=repo,
        from_ref=from_ref,
        to_ref=to_ref,
        source_file=source_file,
        branch=branch,
        since_date=since_date,
        version=version_str,
        title=title,
        app_name=app_name,
        language=lang,
        audience=Audience(audience),
        output_format=OutputFormat(internal_format),
        output_file=output_file,
        render=RenderConfig(
            show_authors=show_authors,
            show_commit_hashes=show_hashes,
            language=lang,
            accent_color=accent_color,
        ),
    )


def _handle_error(exc: Exception) -> None:
    """Convert domain exceptions to user-friendly errors."""
    if isinstance(exc, GitCollectionError):
        git_command_failed(str(exc)).exit()
    elif isinstance(exc, PipelineError):
        UserError(
            summary="Pipeline error",
            reason=str(exc),
            suggestions=["Try 'releasepilot guide' for an interactive workflow"],
            commands=["releasepilot guide"],
        ).exit()
    elif isinstance(exc, StructuredFileError):
        UserError(
            summary="Structured file error",
            reason=str(exc),
            suggestions=["Check the JSON file format and try again"],
        ).exit()
    else:
        UserError(summary="Unexpected error", reason=str(exc)).exit()


def _run_pipeline(settings: Settings, *, dry_run: bool = False) -> str:
    """Run the pipeline with pre-flight validation and empty-release detection."""
    # Pre-flight validation
    err = validate_settings(settings)
    if err:
        err.exit()

    if dry_run:
        return _run_dry(settings)

    progress = _make_cli_progress()
    try:
        output = orchestrator.generate(settings, on_progress=progress)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return ""  # unreachable, _handle_error exits

    # Empty release detection
    if not output.strip() or _is_empty_release(output):
        console.print()
        console.print("[yellow]ℹ No meaningful changes found.[/yellow]")
        console.print()
        console.print("[dim]Possible reasons:[/dim]")
        console.print("  • The selected range or time window has no commits")
        console.print("  • All changes were filtered as noise (merges, WIP, fixups)")
        console.print()
        console.print("[dim]Suggestions:[/dim]")
        console.print("  → Try a wider time range: --since 2025-01-01")
        console.print("  → Try a different branch: --branch main")
        console.print("  → Use 'releasepilot collect' to inspect raw changes")
        console.print("  → Use 'releasepilot guide' for interactive assistance")
        console.print()

    return output


def _run_dry(settings: Settings) -> str:
    """Dry-run: show pipeline summary without rendering."""
    try:
        release_range = orchestrator.build_release_range(settings)
        raw_items = orchestrator.collect(settings, release_range)
        processed_items, stats = orchestrator.process_with_stats(settings, raw_items)
        notes = orchestrator.compose(settings, processed_items, release_range, stats)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return ""

    console.print()
    console.print("[bold]🔍 Dry Run — Pipeline Summary[/bold]")
    console.print()
    console.print(f"  Range:          {release_range.from_ref}..{release_range.to_ref}")
    console.print(f"  Title:          {release_range.display_title}")
    if release_range.version:
        console.print(f"  Version:        {release_range.version}")
    if release_range.release_date:
        console.print(f"  Release date:   {release_range.release_date.isoformat()}")
    if stats.effective_branch:
        console.print(f"  Branch:         {stats.effective_branch}")
    if stats.effective_date_range:
        console.print(f"  Date range:     {stats.effective_date_range}")
    console.print()
    console.print(f"  Raw changes:    {stats.raw}")
    console.print(f"  After filter:   {stats.after_filter}")
    console.print(f"  After dedup:    {stats.after_dedup}")
    console.print(f"  Filtered out:   {stats.filtered_out}")
    console.print(f"  Dedup removed:  {stats.dedup_removed}")
    console.print(f"  Final:          {stats.final}")
    if stats.contributor_count:
        console.print(f"  Contributors:   {stats.contributor_count}")
    if stats.first_commit_date:
        console.print(f"  First commit:   {stats.first_commit_date}")
    if stats.last_commit_date:
        console.print(f"  Last commit:    {stats.last_commit_date}")
    if stats.scopes:
        console.print(f"  Components:     {', '.join(stats.scopes[:15])}")
    if stats.category_counts:
        cat_parts = [f"{c}: {n}" for c, n in sorted(stats.category_counts.items()) if n > 0]
        console.print(f"  Categories:     {', '.join(cat_parts)}")
    console.print()

    if notes.groups:
        console.print("  [bold]Groups:[/bold]")
        for group in notes.groups:
            console.print(f"    {group.display_label}: {len(group.items)}")
    if notes.highlights:
        console.print(f"\n  [bold]Highlights:[/bold] {len(notes.highlights)}")
    if notes.breaking_changes:
        console.print(f"  [bold red]Breaking changes:[/bold red] {len(notes.breaking_changes)}")

    console.print()
    console.print(f"  Audience:       {settings.audience.value}")
    console.print(f"  Format:         {settings.output_format.value}")
    console.print()
    console.print("[dim]Remove --dry-run to generate the full output.[/dim]")

    return ""


def _is_empty_release(output: str) -> bool:
    """Detect if the rendered output represents an empty release.

    Check for both the i18n 'no_notable_changes' label (used by all renderers)
    and a trivial content heuristic.
    """
    from releasepilot.i18n import get_label

    stripped = output.strip()
    if not stripped:
        return True

    # Check all supported languages for the no-changes label.
    langs = ("en", "pl", "de", "fr", "es", "it", "pt", "nl", "uk", "cs")
    return any(get_label("no_notable_changes", lang) in stripped for lang in langs)


# ── CLI Group ────────────────────────────────────────────────────────────────


@click.group()
@click.version_option(__version__, prog_name="releasepilot")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable verbose/debug logging")
def cli(verbose: bool):
    """ReleasePilot — Generate polished release notes from your repository."""
    _install_signal_handlers()
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(name)s %(levelname)s: %(message)s",
    )


# ── generate ─────────────────────────────────────────────────────────────────


@cli.command()
@_common_options
@click.option(
    "--audience",
    type=click.Choice(_ALL_AUDIENCES),
    default=None,
    help="Target audience (default: changelog)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(_ALL_FORMATS),
    default=None,
    help="Output format (default: markdown)",
)
@click.option("--show-authors", is_flag=True, help="Include author names")
@click.option("--show-hashes", is_flag=True, help="Include commit hashes")
def generate(
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
    output_format: str,
    show_authors: bool,
    show_hashes: bool,
):
    """Generate release notes."""
    # Resolve effective values for pre-settings checks
    eff_format = output_format if output_format is not None else "markdown"

    if eff_format in ("pdf", "docx"):
        err = validate_export_format_deps(eff_format)
        if err:
            err.exit()

    settings = _build_settings(
        repo, from_ref, to_ref, source_file, version_str, title,
        branch, since_date, audience, output_format,
        show_authors=show_authors, show_hashes=show_hashes,
        app_name=app_name, lang=lang,
    )

    resolved_audience = settings.audience.value
    resolved_format = eff_format  # pdf/docx not stored in settings directly

    # Executive audience uses a separate rendering pipeline
    if resolved_audience == "executive":
        _run_executive(settings, resolved_format, dry_run)
        return

    # Narrative audiences use the fact-grounded narrative pipeline
    if resolved_audience in ("narrative", "customer-narrative"):
        _run_narrative(settings, resolved_format, dry_run)
        return

    if resolved_format in ("pdf", "docx"):
        _generate_binary(settings, resolved_format, dry_run)
    else:
        output = _run_pipeline(settings, dry_run=dry_run)
        if output:
            click.echo(output)


def _generate_binary(settings: Settings, fmt: str, dry_run: bool) -> None:
    """Generate binary output (PDF/DOCX) and save to file."""
    if dry_run:
        _run_dry(settings)
        return

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        release_range = orchestrator.build_release_range(settings)
        items = orchestrator.collect(settings, release_range)
        items, stats = orchestrator.process_with_stats(settings, items)
        notes = orchestrator.compose(settings, items, release_range, stats)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    ext = ".pdf" if fmt == "pdf" else ".docx"
    default_name = f"RELEASE_NOTES{ext}"
    output_path = settings.output_file or default_name

    err = validate_export_path(output_path, allow_overwrite=True)
    if err:
        err.exit()

    if fmt == "pdf":
        from releasepilot.rendering.pdf import PdfRenderer
        data = PdfRenderer().render_bytes(notes, settings.render)
    else:
        from releasepilot.rendering.docx_renderer import DocxRenderer
        data = DocxRenderer().render_bytes(notes, settings.render)

    _atomic_write_bytes(output_path, data)
    console.print(f"[green]✓[/green] Written to {output_path}")


def _build_executive_brief(settings: Settings):
    """Run the pipeline and compose an ExecutiveBrief."""
    from releasepilot.audience.executive import compose_executive_brief

    release_range = orchestrator.build_release_range(settings)
    items = orchestrator.collect(settings, release_range)
    items, stats = orchestrator.process_with_stats(settings, items)
    notes = orchestrator.compose(settings, items, release_range, stats)

    period = ""
    if settings.since_date:
        from releasepilot.i18n import get_label

        period = get_label("since_date_label", settings.language).format(
            date=settings.since_date,
        )
    return compose_executive_brief(notes, analysis_period=period)


def _run_executive(settings: Settings, output_format: str, dry_run: bool) -> None:
    """Run the executive brief pipeline."""
    if dry_run:
        _run_dry(settings)
        return

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        brief = _build_executive_brief(settings)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    if output_format == "pdf":
        from releasepilot.rendering.executive_pdf import ExecutivePdfRenderer
        data = ExecutivePdfRenderer().render_bytes(brief, lang=settings.language, accent_color=settings.render.accent_color)
        output_path = settings.output_file or "RELEASE_BRIEF.pdf"
        err = validate_export_path(output_path, allow_overwrite=True)
        if err:
            err.exit()
        _atomic_write_bytes(output_path, data)
        console.print(f"[green]✓[/green] Written to {output_path}")
    elif output_format == "docx":
        from releasepilot.rendering.executive_docx import ExecutiveDocxRenderer
        data = ExecutiveDocxRenderer().render_bytes(brief, lang=settings.language, accent_color=settings.render.accent_color)
        output_path = settings.output_file or "RELEASE_BRIEF.docx"
        err = validate_export_path(output_path, allow_overwrite=True)
        if err:
            err.exit()
        _atomic_write_bytes(output_path, data)
        console.print(f"[green]✓[/green] Written to {output_path}")
    elif output_format == "json":
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer
        click.echo(ExecutiveMarkdownRenderer().render_json(brief))
    else:
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer
        click.echo(ExecutiveMarkdownRenderer().render(brief, lang=settings.language))


def _build_narrative_brief(settings: Settings):
    """Run the pipeline and compose a NarrativeBrief."""
    from releasepilot.audience.narrative import compose_narrative

    release_range = orchestrator.build_release_range(settings)
    items = orchestrator.collect(settings, release_range)
    items, stats = orchestrator.process_with_stats(settings, items)
    notes = orchestrator.compose(settings, items, release_range, stats)

    customer_facing = settings.audience.value == "customer-narrative"
    return compose_narrative(notes, customer_facing=customer_facing)


def _run_narrative(settings: Settings, output_format: str, dry_run: bool) -> None:
    """Run the narrative brief pipeline."""
    if dry_run:
        _run_dry(settings)
        return

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        brief = _build_narrative_brief(settings)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    if output_format == "pdf":
        from releasepilot.rendering.narrative_pdf import NarrativePdfRenderer
        data = NarrativePdfRenderer().render_bytes(brief, lang=settings.language, accent_color=settings.render.accent_color)
        output_path = settings.output_file or "NARRATIVE_SUMMARY.pdf"
        err = validate_export_path(output_path, allow_overwrite=True)
        if err:
            err.exit()
        _atomic_write_bytes(output_path, data)
        console.print(f"[green]✓[/green] Written to {output_path}")
    elif output_format == "docx":
        from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer
        data = NarrativeDocxRenderer().render_bytes(brief, lang=settings.language, accent_color=settings.render.accent_color)
        output_path = settings.output_file or "NARRATIVE_SUMMARY.docx"
        err = validate_export_path(output_path, allow_overwrite=True)
        if err:
            err.exit()
        _atomic_write_bytes(output_path, data)
        console.print(f"[green]✓[/green] Written to {output_path}")
    elif output_format == "json":
        from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer
        click.echo(NarrativeMarkdownRenderer().render_json(brief))
    else:
        from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer
        click.echo(NarrativeMarkdownRenderer().render(brief, lang=settings.language))


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
        repo, from_ref, to_ref, source_file, version_str, title,
        branch, since_date, audience, output_format="plaintext",
        app_name=app_name, lang=lang,
    )

    # Executive preview uses the executive markdown renderer
    if audience == "executive":
        err = validate_settings(settings)
        if err:
            err.exit()
        try:
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
        repo, from_ref, to_ref, source_file, version_str, title,
        branch, since_date, app_name=app_name, lang=lang,
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
        repo, from_ref, to_ref, source_file, version_str, title,
        branch, since_date, app_name=app_name, lang=lang,
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


# ── export ───────────────────────────────────────────────────────────────────


@cli.command()
@_common_options
@click.option(
    "--audience",
    type=click.Choice(_ALL_AUDIENCES),
    default=None,
    help="Target audience (default: changelog)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(_ALL_FORMATS),
    default=None,
    help="Output format (default: markdown)",
)
@click.option("-o", "--output", "output_file", required=True, help="Output file path")
@click.option("--show-authors", is_flag=True, help="Include author names")
@click.option("--show-hashes", is_flag=True, help="Include commit hashes")
def export(
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
    output_format: str,
    output_file: str,
    show_authors: bool,
    show_hashes: bool,
):
    """Write release notes to a file."""
    # Resolve effective values for pre-settings checks
    eff_format = output_format if output_format is not None else "markdown"

    # Validate export format deps early
    if eff_format in ("pdf", "docx"):
        err = validate_export_format_deps(eff_format)
        if err:
            err.exit()

    # Validate output path
    err = validate_export_path(output_file, allow_overwrite=True)
    if err:
        err.exit()

    settings = _build_settings(
        repo, from_ref, to_ref, source_file, version_str, title,
        branch, since_date, audience, output_format, output_file=output_file,
        show_authors=show_authors, show_hashes=show_hashes,
        app_name=app_name, lang=lang,
    )

    if dry_run:
        _run_dry(settings)
        return

    resolved_audience = settings.audience.value
    resolved_format = eff_format

    # Executive audience uses a separate rendering pipeline
    if resolved_audience == "executive":
        _export_executive(settings, resolved_format, output_file)
        return

    # Narrative audiences use the fact-grounded narrative pipeline
    if resolved_audience in ("narrative", "customer-narrative"):
        _export_narrative(settings, resolved_format, output_file)
        return

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        release_range = orchestrator.build_release_range(settings)
        items = orchestrator.collect(settings, release_range)
        items, stats = orchestrator.process_with_stats(settings, items)
        notes = orchestrator.compose(settings, items, release_range, stats)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    if resolved_format in ("pdf", "docx"):
        if resolved_format == "pdf":
            from releasepilot.rendering.pdf import PdfRenderer
            data = PdfRenderer().render_bytes(notes, settings.render)
        else:
            from releasepilot.rendering.docx_renderer import DocxRenderer
            data = DocxRenderer().render_bytes(notes, settings.render)
        _atomic_write_bytes(output_file, data)
    else:
        output = orchestrator.render(settings, notes)
        _atomic_write_text(output_file, output)

    console.print(f"[green]✓[/green] Written to {output_file}")


def _export_executive(settings: Settings, output_format: str, output_file: str) -> None:
    """Export an executive brief to a file."""
    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        brief = _build_executive_brief(settings)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    if output_format == "pdf":
        from releasepilot.rendering.executive_pdf import ExecutivePdfRenderer
        _atomic_write_bytes(output_file, ExecutivePdfRenderer().render_bytes(brief, lang=settings.language, accent_color=settings.render.accent_color))
    elif output_format == "docx":
        from releasepilot.rendering.executive_docx import ExecutiveDocxRenderer
        _atomic_write_bytes(output_file, ExecutiveDocxRenderer().render_bytes(brief, lang=settings.language, accent_color=settings.render.accent_color))
    elif output_format == "json":
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer
        _atomic_write_text(output_file, ExecutiveMarkdownRenderer().render_json(brief))
    else:
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer
        _atomic_write_text(output_file, ExecutiveMarkdownRenderer().render(brief))

    console.print(f"[green]✓[/green] Written to {output_file}")


def _export_narrative(settings: Settings, output_format: str, output_file: str) -> None:
    """Export a narrative brief to a file."""
    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        brief = _build_narrative_brief(settings)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    if output_format == "pdf":
        from releasepilot.rendering.narrative_pdf import NarrativePdfRenderer
        _atomic_write_bytes(output_file, NarrativePdfRenderer().render_bytes(brief, lang=settings.language, accent_color=settings.render.accent_color))
    elif output_format == "docx":
        from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer
        _atomic_write_bytes(output_file, NarrativeDocxRenderer().render_bytes(brief, lang=settings.language, accent_color=settings.render.accent_color))
    elif output_format == "json":
        from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer
        _atomic_write_text(output_file, NarrativeMarkdownRenderer().render_json(brief))
    else:
        from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer
        _atomic_write_text(output_file, NarrativeMarkdownRenderer().render(brief, lang=settings.language))

    console.print(f"[green]✓[/green] Written to {output_file}")


# ── multi ─────────────────────────────────────────────────────────────────


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
                    brief = _build_executive_brief(settings)
                    from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer
                    if output_format == "json":
                        output = ExecutiveMarkdownRenderer().render_json(brief)
                    else:
                        output = ExecutiveMarkdownRenderer().render(brief, lang=lang)
                elif is_narrative:
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
            continue

        if not output.strip():
            console.print(f"  [yellow]⚠ No changes found for {repo_label}[/yellow]")
            continue

        console.print("  [green]✓[/green] Done")

        if output_dir:
            ext = {
                "markdown": ".md", "plaintext": ".txt", "json": ".json",
            }[output_format]
            out_path = Path(output_dir) / f"{repo_label}{ext}"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(str(out_path), output)
            console.print(f"  [green]✓[/green] Saved to {out_path}")
        else:
            combined_parts.append(output)

    if not output_dir and combined_parts:
        click.echo("\n".join(combined_parts))


# ── guide ─────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("repo_path", default=".", required=False)
@click.option(
    "--reset-preferences", is_flag=True, default=False,
    help="Clear saved guided-workflow preferences and exit.",
)
def guide(repo_path: str, reset_preferences: bool):
    """Interactive guided workflow for generating release notes.

    Designed for QA, testers, and non-developer users who may not know
    exact git refs or tags. Walks through repository inspection, branch
    selection, time range, and audience step by step.

    REPO_PATH is the path to a local git repository or a remote URL
    (default: current directory). Remote URLs are cloned automatically.
    """
    if reset_preferences:
        from releasepilot.cli.preferences import reset_preferences as _reset

        _reset()
        click.echo("Preferences cleared.")
        return

    from releasepilot.cli.guide import run_guide

    run_guide(repo_path)


# ── Entry point ──────────────────────────────────────────────────────────────


def main():
    cli()
