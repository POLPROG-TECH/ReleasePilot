"""Shared CLI helpers — options, settings builder, error handling, pipeline runners."""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from pathlib import Path

import click
from rich.console import Console

from releasepilot.cli.errors import UserError, git_command_failed
from releasepilot.cli.validators import (
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
_ALL_AUDIENCES = [
    "technical",
    "user",
    "summary",
    "changelog",
    "customer",
    "executive",
    "narrative",
    "customer-narrative",
]


# ── Atomic write helpers ────────────────────────────────────────────────────


def _atomic_write_text(path: str, content: str) -> None:
    """Write *content* to *path* atomically (write-to-temp then rename)."""
    target = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd = -1  # mark as closed
        os.replace(tmp, target)
    except BaseException:
        if fd >= 0:
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
        fd = -1  # mark as closed
        os.replace(tmp, target)
    except BaseException:
        if fd >= 0:
            with _SuppressOs():
                os.close(fd)
        with _SuppressOs():
            os.unlink(tmp)
        raise


class _SuppressOs:
    """Tiny context manager that suppresses OSError.

    Equivalent to ``contextlib.suppress(OSError)`` but kept for backward
    compatibility with existing call sites.
    """

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return isinstance(a[1], OSError)


# Also export a clean alias using contextlib.
suppress_os = contextlib.suppress(OSError)


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
        "--language",
        "lang",
        default=None,
        help="Output language (en, pl, de, fr, es, it, pt, nl, uk, cs)",
    )(fn)
    fn = click.option("--branch", default="", help="Branch to analyze (for date-range mode)")(fn)
    fn = click.option(
        "--since",
        "since_date",
        default="",
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
    internal_format = (
        output_format if output_format in ("markdown", "plaintext", "json") else "markdown"
    )
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


def _handle_error(exc: Exception, *, exit_on_error: bool = True) -> UserError:
    """Convert domain exceptions to user-friendly errors.

    When *exit_on_error* is True (default, CLI usage), displays and exits.
    When False (library/programmatic usage), returns the UserError without exiting.
    """
    if isinstance(exc, GitCollectionError):
        err = git_command_failed(str(exc))
    elif isinstance(exc, PipelineError):
        err = UserError(
            summary="Pipeline error",
            reason=str(exc),
            suggestions=["Try 'releasepilot guide' for an interactive workflow"],
            commands=["releasepilot guide"],
        )
    elif isinstance(exc, StructuredFileError):
        err = UserError(
            summary="Structured file error",
            reason=str(exc),
            suggestions=["Check the JSON file format and try again"],
        )
    else:
        err = UserError(summary="Unexpected error", reason=str(exc))

    if exit_on_error:
        err.exit()
    return err


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
    and a trivial content heuristic.  For JSON output, also check the
    ``total_changes`` field.
    """
    from releasepilot.i18n import get_label

    stripped = output.strip()
    if not stripped:
        return True

    # JSON format: check total_changes field
    if stripped.startswith("{"):
        try:
            import json

            data = json.loads(stripped)
            if isinstance(data, dict) and data.get("total_changes", -1) == 0:
                return True
        except (json.JSONDecodeError, ValueError):
            pass

    # Check all supported languages for the no-changes label.
    langs = ("en", "pl", "de", "fr", "es", "it", "pt", "nl", "uk", "cs")
    return any(get_label("no_notable_changes", lang) in stripped for lang in langs)
