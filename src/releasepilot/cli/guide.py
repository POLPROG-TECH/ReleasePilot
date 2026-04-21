"""Guided interactive workflow for ReleasePilot.

Provides a step-by-step interactive experience for users who don't know
exact git refs or tags - testers, QA, product managers, etc.

All interactive prompting is confined to this module (via the ``prompts``
helper).  The core pipeline remains fully non-interactive for CI/CD use.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console

from releasepilot.cli.guide_steps import (
    _AUDIENCE_CHOICES,  # noqa: F401 - re-exported for backward compat
    _FORMAT_CHOICES,  # noqa: F401
    _FORMAT_CHOICES_EXECUTIVE,  # noqa: F401
    _FORMAT_CHOICES_NARRATIVE,  # noqa: F401
    _LANGUAGE_CHOICES,  # noqa: F401
    _TIME_RANGE_CHOICES,  # noqa: F401
    _clamp_to_repo_history,  # noqa: F401
    _confirm_overwrite_or_rename,  # noqa: F401
    _prompt_valid_branch,  # noqa: F401
    _prompt_valid_date,  # noqa: F401
    _step_audience,
    _step_branch_selection,
    _step_changelog_detection,
    _step_custom_title,
    _step_display_and_export,
    _step_display_and_export_executive,
    _step_display_and_export_narrative,
    _step_format,
    _step_format_executive,
    _step_format_narrative,
    _step_inspect,
    _step_language,
    _step_time_range,
)
from releasepilot.cli.prompts import confirm
from releasepilot.config.settings import RenderConfig, Settings
from releasepilot.domain.enums import Audience, OutputFormat
from releasepilot.pipeline import orchestrator
from releasepilot.pipeline.orchestrator import PipelineError
from releasepilot.sources.git import GitCollectionError
from releasepilot.sources.structured import StructuredFileError

console = Console(stderr=True)

# ── Progress reporting helpers ───────────────────────────────────────────────


class _ProgressTracker:
    """Encapsulated progress state (avoids global mutable state)."""

    def __init__(self) -> None:
        self.start_time: float = 0.0

    def make_callback(self):
        """Create a progress callback that prints stage updates to the console."""
        import time

        self.start_time = time.monotonic()

        def _on_progress(stage: str, detail: str = "", current: int = 0, total: int = 0) -> None:
            elapsed = time.monotonic() - self.start_time
            elapsed_str = f"[dim]({elapsed:.1f}s)[/dim]"

            if detail:
                console.print(f"  [cyan]⟳[/cyan] {stage} - {detail} {elapsed_str}")
            else:
                console.print(f"  [cyan]⟳[/cyan] {stage} {elapsed_str}")

        return _on_progress

    def finish(self) -> None:
        """Print a completion line after the pipeline finishes."""
        import time

        elapsed = time.monotonic() - self.start_time
        console.print(f"  [green]✓[/green] Pipeline complete [dim]({elapsed:.1f}s)[/dim]")
        console.print()


# Keep module-level aliases for backward compatibility but delegate to tracker
_progress_start_time: float = 0.0
_default_tracker = _ProgressTracker()


def _make_progress_callback():
    """Create a progress callback that prints stage updates to the console."""
    return _default_tracker.make_callback()


def _finish_progress() -> None:
    """Print a completion line after the pipeline finishes."""
    _default_tracker.finish()


# ── URL pattern for detecting repository links ──────────────────────────────

_REPO_URL_RE = re.compile(
    r"^(https?://[^\s]+\.git|https?://github\.com/[^\s]+|git@[^\s]+\.git)$",
)

# ── Analysis period formatting ───────────────────────────────────────────────


def _format_analysis_period(descriptor: str, lang: str = "en") -> str:
    """Convert a period descriptor into a translated, human-readable string.

    Descriptor formats:
    - ``"days:N"``           → "Last N days" (translated)
    - ``"days:N:YYYY-MM-DD"``→ "Last N days (effective: since YYYY-MM-DD)"
    - ``"since:YYYY-MM-DD"`` → "since YYYY-MM-DD" (translated)
    - ``""``                 → ""
    """
    if not descriptor:
        return ""

    from releasepilot.i18n import get_label

    if descriptor.startswith("days:"):
        parts = descriptor.split(":")
        days = parts[1]
        period = get_label("last_n_days", lang).format(days=days)
        if len(parts) >= 3:
            effective_date = parts[2]
            note = get_label("effective_range_note", lang).format(
                date=effective_date,
            )
            return f"{period} {note}"
        return period

    if descriptor.startswith("since:"):
        parts = descriptor.split(":", 1)
        d = parts[1]
        # "since:" may also have ":effective_date" appended
        sub = d.split(":")
        since_str = get_label("since_date_label", lang).format(date=sub[0])
        if len(sub) >= 2:
            note = get_label("effective_range_note", lang).format(date=sub[1])
            return f"{since_str} {note}"
        return since_str

    return descriptor


# ── Main entry point ─────────────────────────────────────────────────────────


def run_guide(repo_path: str) -> None:
    """Run the full guided workflow."""
    console.print()
    console.print("[bold blue]🚀 ReleasePilot - Guided Release Notes[/bold blue]")
    console.print()

    # ── Step 0: Handle repository URL (clone if needed) ─────────────────
    cloned_dir: str | None = None
    if _REPO_URL_RE.match(repo_path):
        cloned_dir = _step_clone_repo(repo_path)
        if not cloned_dir:
            raise SystemExit(1)
        repo_path = cloned_dir

    try:
        _run_guide_inner(repo_path)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Exiting guide.[/yellow]")
        raise SystemExit(130) from None
    finally:
        if cloned_dir:
            _step_cleanup_clone(cloned_dir)


def _run_guide_inner(repo_path: str) -> None:
    """Core guided workflow (after repo_path is resolved to a local path)."""
    from releasepilot.cli.preferences import get_preferred_default, record_choice

    # ── Explain smart-defaults behaviour ────────────────────────────────
    console.print(
        "[dim]💡 Tip: Choices you repeat 3+ times become remembered defaults, "
        "making future runs faster.[/dim]",
    )
    console.print(
        "[dim]   Preferences are stored in ~/.config/releasepilot/preferences.json "
        "(set RELEASEPILOT_NO_PREFS=1 to disable).[/dim]",
    )
    console.print()

    # ── Step 1: Inspect repository ──────────────────────────────────────
    with console.status("[bold cyan]Inspecting repository...[/bold cyan]"):
        inspection = _step_inspect(repo_path)
    if not inspection.is_valid_repo:
        console.print(f"[red]✗[/red] {inspection.error}")
        raise SystemExit(1)

    console.print(f"[green]✓[/green] Repository: [bold]{inspection.path}[/bold]")

    # ── Step 2: Check for existing changelog ────────────────────────────
    source_file = _step_changelog_detection(inspection)

    # ── Step 3: Branch selection (if using git) ─────────────────────────
    branch = ""
    since_date = ""
    period_descriptor = ""

    if not source_file:
        branch = _step_branch_selection(inspection)
        record_choice("branch", branch)

        # ── Step 4: Time range ──────────────────────────────────────────
        since_date, period_descriptor = _step_time_range(inspection.path, branch)

    # ── Step 5: Audience ────────────────────────────────────────────────
    audience = _step_audience(get_preferred_default)
    record_choice("audience", audience.value)

    # ── Step 6: Output format ───────────────────────────────────────────
    is_executive = audience == Audience.EXECUTIVE
    is_customer = audience == Audience.CUSTOMER
    is_narrative = audience in (Audience.NARRATIVE, Audience.CUSTOMER_NARRATIVE)
    if is_executive:
        exec_format = _step_format_executive(get_preferred_default)
        record_choice("format", exec_format)
        # Validate dependencies for binary formats before pipeline work.
        if exec_format in ("pdf", "docx"):
            from releasepilot.cli.validators import validate_export_format_deps

            err = validate_export_format_deps(exec_format)
            if err:
                err.display()
                raise SystemExit(1)
    elif is_narrative:
        narr_format = _step_format_narrative(get_preferred_default)
        record_choice("format", narr_format)
        if narr_format in ("pdf", "docx"):
            from releasepilot.cli.validators import validate_export_format_deps

            err = validate_export_format_deps(narr_format)
            if err:
                err.display()
                raise SystemExit(1)
    else:
        output_format = _step_format(get_preferred_default)
        record_choice("format", output_format.value)

    # ── Step 7: Custom title / subtitle ────────────────────────────────
    repo_name = Path(inspection.path).resolve().name
    custom_title = _step_custom_title(repo_name)

    # ── Step 8: Language ────────────────────────────────────────────────
    language = _step_language(get_preferred_default)
    record_choice("language", language)

    # ── Step 9: Generate ────────────────────────────────────────────────
    console.print()

    # Customer / customer-narrative modes hide technical details
    if is_customer or audience == Audience.CUSTOMER_NARRATIVE:
        render_cfg = RenderConfig(
            show_authors=False,
            show_commit_hashes=False,
            show_scope=False,
            show_pr_links=False,
            language=language,
        )
    else:
        render_cfg = RenderConfig(show_authors=True, language=language)

    settings = Settings(
        repo_path=inspection.path,
        source_file=source_file,
        branch=branch,
        since_date=since_date,
        audience=audience,
        output_format=OutputFormat.MARKDOWN if (is_executive or is_narrative) else output_format,
        app_name=repo_name,
        title=custom_title,
        language=language,
        render=render_cfg,
    )

    # Populate branch/date info on stats for transparency
    _branch_for_stats = branch
    _date_for_stats = since_date

    try:
        progress_cb = _make_progress_callback()

        if is_executive:
            from releasepilot.audience.executive import compose_executive_brief

            release_range = orchestrator.build_release_range(settings, progress_cb)
            items = orchestrator.collect(settings, release_range, progress_cb)
            items, stats = orchestrator.process_with_stats(settings, items, progress_cb)
            stats.effective_branch = _branch_for_stats
            stats.effective_date_range = f"since {_date_for_stats}" if _date_for_stats else ""
            notes = orchestrator.compose(settings, items, release_range, stats, progress_cb)
            progress_cb("Composing executive brief")
            brief = compose_executive_brief(
                notes,
                analysis_period=_format_analysis_period(
                    period_descriptor,
                    language,
                ),
            )
            _finish_progress()
            _step_display_and_export_executive(
                brief, exec_format, language, settings.render.accent_color
            )
        elif is_narrative:
            from releasepilot.audience.narrative import compose_narrative

            release_range = orchestrator.build_release_range(settings, progress_cb)
            items = orchestrator.collect(settings, release_range, progress_cb)
            items, stats = orchestrator.process_with_stats(settings, items, progress_cb)
            stats.effective_branch = _branch_for_stats
            stats.effective_date_range = f"since {_date_for_stats}" if _date_for_stats else ""
            notes = orchestrator.compose(settings, items, release_range, stats, progress_cb)
            progress_cb("Composing narrative brief")
            customer_facing = audience == Audience.CUSTOMER_NARRATIVE
            brief = compose_narrative(notes, customer_facing=customer_facing)
            _finish_progress()
            _step_display_and_export_narrative(
                brief, narr_format, language, settings.render.accent_color
            )
        else:
            release_range = orchestrator.build_release_range(settings, progress_cb)
            items = orchestrator.collect(settings, release_range, progress_cb)
            items, stats = orchestrator.process_with_stats(settings, items, progress_cb)
            stats.effective_branch = _branch_for_stats
            stats.effective_date_range = f"since {_date_for_stats}" if _date_for_stats else ""
            notes = orchestrator.compose(settings, items, release_range, stats, progress_cb)
            output = orchestrator.render(settings, notes, progress_cb)
            _finish_progress()
            _step_display_and_export(output, output_format, audience)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1) from exc


# ── Repository URL clone/cleanup ─────────────────────────────────────────


def _step_clone_repo(url: str) -> str | None:
    """Clone a remote repository to a temporary directory.

    Returns the path to the cloned repository, or None on failure.
    Only HTTPS URLs are allowed for security.
    """
    # Reject non-HTTPS URLs to prevent git protocol exploits
    if not url.startswith("https://"):
        console.print("[red]✗ Only HTTPS repository URLs are allowed for security reasons.[/red]")
        console.print(f"   Received: [cyan]{url}[/cyan]")
        console.print("   [dim]Hint: Convert SSH URLs to HTTPS format.[/dim]")
        return None

    clone_dir = Path(tempfile.mkdtemp(prefix="releasepilot-"))
    target = clone_dir / "repo"

    console.print("[bold]📥 Cloning repository...[/bold]")
    console.print(f"   URL:  [cyan]{url}[/cyan]")
    console.print(f"   Into: [cyan]{target}[/cyan]")
    console.print()

    try:
        with console.status("[bold cyan]Cloning repository...[/bold cyan]"):
            result = subprocess.run(
                ["git", "clone", "--depth=200", url, str(target)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        if result.returncode != 0:
            console.print(f"[red]✗ Clone failed:[/red] {result.stderr.strip()}")
            shutil.rmtree(clone_dir, ignore_errors=True)
            return None
    except subprocess.TimeoutExpired:
        console.print("[red]✗ Clone timed out after 120 seconds.[/red]")
        shutil.rmtree(clone_dir, ignore_errors=True)
        return None
    except FileNotFoundError:
        console.print("[red]✗ git is not installed or not found in PATH.[/red]")
        shutil.rmtree(clone_dir, ignore_errors=True)
        return None

    console.print("[green]✓[/green] Repository cloned successfully.")
    console.print()
    return str(target)


def _step_cleanup_clone(cloned_dir: str) -> None:
    """Ask the user whether to remove the cloned repository."""
    console.print()
    remove = confirm(
        f"Remove cloned repository at '{cloned_dir}'?",
        default=True,
    )
    if remove:
        shutil.rmtree(cloned_dir, ignore_errors=True)
        # Also remove the parent temp dir if empty
        parent = Path(cloned_dir).parent
        if parent.exists() and not list(parent.iterdir()):
            parent.rmdir()
        console.print("[green]✓[/green] Cloned repository removed.")
    else:
        console.print(f"[dim]Cloned repository kept at: {cloned_dir}[/dim]")
