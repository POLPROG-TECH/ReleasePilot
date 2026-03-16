"""Guided interactive workflow for ReleasePilot.

Provides a step-by-step interactive experience for users who don't know
exact git refs or tags — testers, QA, product managers, etc.

All interactive prompting is confined to this module (via the ``prompts``
helper).  The core pipeline remains fully non-interactive for CI/CD use.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from releasepilot.cli.prompts import confirm, select_one, text_prompt
from releasepilot.config.settings import RenderConfig, Settings
from releasepilot.domain.enums import Audience, OutputFormat
from releasepilot.pipeline import orchestrator
from releasepilot.pipeline.orchestrator import PipelineError
from releasepilot.sources.git import GitCollectionError
from releasepilot.sources.inspector import RepoInspection, inspect_repo
from releasepilot.sources.structured import StructuredFileError

console = Console(stderr=True)

# ── Progress reporting helpers ───────────────────────────────────────────────

_progress_start_time: float = 0.0


def _make_progress_callback():
    """Create a progress callback that prints stage updates to the console."""
    import time

    global _progress_start_time  # noqa: PLW0603
    _progress_start_time = time.monotonic()

    def _on_progress(stage: str, detail: str = "", current: int = 0, total: int = 0) -> None:
        elapsed = time.monotonic() - _progress_start_time
        elapsed_str = f"[dim]({elapsed:.1f}s)[/dim]"

        if detail:
            console.print(f"  [cyan]⟳[/cyan] {stage} — {detail} {elapsed_str}")
        else:
            console.print(f"  [cyan]⟳[/cyan] {stage} {elapsed_str}")

    return _on_progress


def _finish_progress() -> None:
    """Print a completion line after the pipeline finishes."""
    import time

    elapsed = time.monotonic() - _progress_start_time
    console.print(f"  [green]✓[/green] Pipeline complete [dim]({elapsed:.1f}s)[/dim]")
    console.print()

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

# ── Choice data (label, value) ──────────────────────────────────────────────

_TIME_RANGE_CHOICES: list[tuple[str, int | str]] = [
    ("Last 7 days", 7),
    ("Last 14 days", 14),
    ("Last 30 days", 30),
    ("Last 60 days", 60),
    ("Last 90 days", 90),
    ("Custom date range", "custom"),
]

_AUDIENCE_CHOICES: list[tuple[str, Audience]] = [
    ("Standard changelog", Audience.CHANGELOG),
    ("User-facing / What's New", Audience.USER),
    ("Technical / engineering notes", Audience.TECHNICAL),
    ("Concise summary", Audience.SUMMARY),
    ("Customer-facing product update", Audience.CUSTOMER),
    ("Executive / management brief", Audience.EXECUTIVE),
    ("Narrative summary (readable prose)", Audience.NARRATIVE),
    ("Customer narrative (client-ready prose)", Audience.CUSTOMER_NARRATIVE),
]

_FORMAT_CHOICES: list[tuple[str, OutputFormat]] = [
    ("Markdown", OutputFormat.MARKDOWN),
    ("Plain text", OutputFormat.PLAINTEXT),
    ("JSON", OutputFormat.JSON),
]

_FORMAT_CHOICES_EXECUTIVE: list[tuple[str, str]] = [
    ("PDF (recommended for executives)", "pdf"),
    ("DOCX (Word document)", "docx"),
    ("Markdown", "markdown"),
    ("JSON", "json"),
]

_FORMAT_CHOICES_NARRATIVE: list[tuple[str, str]] = [
    ("PDF (polished document)", "pdf"),
    ("DOCX (Word document)", "docx"),
    ("Markdown", "markdown"),
    ("Plain text", "plaintext"),
    ("JSON", "json"),
]

_LANGUAGE_CHOICES: list[tuple[str, str]] = [
    ("English", "en"),
    ("Polish / Polski", "pl"),
    ("German / Deutsch", "de"),
    ("French / Français", "fr"),
    ("Spanish / Español", "es"),
    ("Italian / Italiano", "it"),
    ("Portuguese / Português", "pt"),
    ("Dutch / Nederlands", "nl"),
    ("Ukrainian / Українська", "uk"),
    ("Czech / Čeština", "cs"),
]


def run_guide(repo_path: str) -> None:
    """Run the full guided workflow."""
    console.print()
    console.print("[bold blue]🚀 ReleasePilot — Guided Release Notes[/bold blue]")
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
                    period_descriptor, language,
                ),
            )
            _finish_progress()
            _step_display_and_export_executive(brief, exec_format, language, settings.render.accent_color)
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
            _step_display_and_export_narrative(brief, narr_format, language, settings.render.accent_color)
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


# ── Step implementations ─────────────────────────────────────────────────


def _step_inspect(repo_path: str) -> RepoInspection:
    console.print(f"Inspecting repository at [cyan]{Path(repo_path).resolve()}[/cyan]...")
    return inspect_repo(repo_path)


def _step_changelog_detection(inspection: RepoInspection) -> str:
    """Check for changelog files and ask whether to use them."""
    if not inspection.changelog_files:
        console.print("[dim]No existing changelog or release notes files found.[/dim]")
        if inspection.has_commits:
            console.print("Will generate release notes from commit history.")
        else:
            console.print("[yellow]⚠ No commits found in this repository.[/yellow]")
        console.print()
        return ""

    console.print()
    console.print("[bold]📄 Found existing release documentation:[/bold]")
    for f in inspection.changelog_files:
        console.print(f"   • {f}")
    console.print()
    console.print(
        "[yellow]⚠ Note: existing release documentation may be outdated or "
        "incomplete. Review it before relying on it.[/yellow]",
    )
    console.print()

    # Check if any is a JSON file we can parse as structured input
    json_files = [f for f in inspection.changelog_files if f.endswith(".json")]
    md_files = [f for f in inspection.changelog_files if not f.endswith(".json")]

    if json_files:
        use_it = confirm(
            f"Use '{json_files[0]}' as structured input? (may not be fully up to date)",
            default=False,
        )
        if use_it:
            return str(Path(inspection.path) / json_files[0])

    if md_files:
        console.print("[dim]Existing markdown changelogs cannot be used as structured input.[/dim]")
        console.print("Will generate fresh release notes from commit history instead.")
        console.print()

    return ""


def _step_branch_selection(inspection: RepoInspection) -> str:
    """Guide the user through branch selection."""
    if not inspection.branches:
        console.print("[yellow]No branches detected. Using HEAD.[/yellow]")
        return "HEAD"

    default = inspection.default_branch or inspection.current_branch

    # Few branches → show a selectable list
    if len(inspection.branches) <= 10:
        choices: list[tuple[str, str]] = [(b, b) for b in inspection.branches]
        default_idx = 0
        for i, (_, val) in enumerate(choices):
            if val == default:
                default_idx = i
                break
        choices.append(("Other (enter manually)", "__other__"))

        result = select_one(
            "🌿 Branch selection",
            choices,
            default_index=default_idx,
        )

        if result == "__other__":
            return _prompt_valid_branch(inspection.branches)
        return result

    # Many branches → confirm default, or ask for manual input
    console.print("[bold]🌿 Branch selection[/bold]")
    console.print(f"   {len(inspection.branches)} branches available")
    if default:
        console.print(f"   Default: [green]{default}[/green]")
    console.print()

    if default and confirm(f"Use branch '{default}'?", default=True):
        return default

    return _prompt_valid_branch(inspection.branches)


def _prompt_valid_branch(branches: list[str] | tuple[str, ...]) -> str:
    """Prompt for a branch name, looping until a valid one is entered."""
    while True:
        branch = text_prompt("Enter branch name")
        if branch in branches:
            return branch
        console.print(
            f"[red]✗ Branch '{branch}' does not exist locally.[/red]",
        )
        if len(branches) <= 15:
            console.print(
                f"[dim]  Available branches: {', '.join(branches)}[/dim]",
            )
        else:
            console.print(
                f"[dim]  {len(branches)} branches available. "
                f"Examples: {', '.join(list(branches)[:5])}…[/dim]",
            )
        console.print()


def _prompt_valid_date() -> str:
    """Prompt for a date (YYYY-MM-DD) or a number of days back.

    Accepts two input formats:
    - A date string like ``2025-01-15``
    - A number like ``30`` (meaning 30 days back from today)

    Loops until valid input is provided.
    """
    while True:
        raw = text_prompt(
            "Enter start date (YYYY-MM-DD) or number of days back (e.g. 30)",
        )
        raw = raw.strip()
        if not raw:
            console.print("[red]✗ Please enter a date or number of days.[/red]")
            continue

        # Try as number of days first
        if raw.isdigit():
            days = int(raw)
            if days < 1:
                console.print("[red]✗ Number of days must be at least 1.[/red]")
                continue
            if days > 3650:
                console.print("[red]✗ Maximum is 3650 days (≈10 years).[/red]")
                continue
            result = (date.today() - timedelta(days=days)).isoformat()
            console.print(f"[dim]   → Interpreted as: since {result} ({days} days back)[/dim]")
            return result

        # Try as ISO date
        try:
            parsed = date.fromisoformat(raw)
            if parsed > date.today():
                console.print("[red]✗ Date is in the future. Enter a past date.[/red]")
                continue
            return parsed.isoformat()
        except ValueError:
            console.print(
                f"[red]✗ '{raw}' is not a valid date or number of days. "
                "Use YYYY-MM-DD format (e.g. 2025-01-15) or a number (e.g. 30).[/red]",
            )


def _step_time_range(repo_path: str, branch: str = "") -> tuple[str, str]:
    """Guide the user through time range selection.

    Detects the repository's first commit date and warns if the
    selected range extends beyond available history.

    Returns:
        A tuple of (effective_date, period_descriptor) where
        period_descriptor is ``"days:N"`` for N-day ranges or
        ``"since:YYYY-MM-DD"`` for custom dates.  When the effective
        date differs from the requested date (clamped to repo history),
        the descriptor is ``"days:N:YYYY-MM-DD"`` where the third part
        is the effective start date.
    """
    result = select_one(
        "📅 Time range",
        _TIME_RANGE_CHOICES,
        default_index=2,  # Last 30 days
        hint="Select a time window for commit analysis",
    )

    if result == "custom":
        custom_date = _prompt_valid_date()
        requested = custom_date
        label = f"since {custom_date}"
        descriptor = f"since:{custom_date}"
    else:
        days = int(result)
        requested = (date.today() - timedelta(days=days)).isoformat()
        label = f"last {days} days"
        descriptor = f"days:{days}"

    # Check whether the requested range exceeds repository history
    effective = _clamp_to_repo_history(requested, repo_path, branch)

    if effective != requested:
        console.print(
            f"   → Requested: [cyan]{label}[/cyan] (since {requested})",
        )
        console.print(
            f"   → Effective: since [cyan]{effective}[/cyan] "
            "(adjusted to first available commit)",
        )
        # Append the effective date so the document can show both
        descriptor = f"{descriptor}:{effective}"
    else:
        console.print(f"   → Analysing [cyan]{label}[/cyan] (since {effective})")
    console.print()
    return effective, descriptor


def _clamp_to_repo_history(since: str, repo_path: str, branch: str = "") -> str:
    """Warn and adjust if the requested date predates the first commit."""
    from releasepilot.sources.git import GitSourceCollector

    try:
        git = GitSourceCollector(repo_path)
        # Use branch-specific history when a branch is selected so the
        # warning is accurate for the analysis scope.
        first_date_raw = git.first_commit_date(branch=branch)
        if not first_date_raw:
            return since

        # Parse just the date portion (ISO string may include time+tz)
        first_date = date.fromisoformat(first_date_raw[:10])
        requested = date.fromisoformat(since[:10])

        if requested < first_date:
            effective = first_date.isoformat()
            scope = f"on branch '{branch}'" if branch else "in this repository"
            console.print(
                f"[yellow]   ⚠ Requested date ({since}) is before the first "
                f"commit {scope} ({effective}).[/yellow]",
            )
            console.print(
                "[yellow]     Analysis will start from the first available "
                "commit instead.[/yellow]",
            )
            return effective
    except (ValueError, TypeError):
        pass  # If date parsing fails, proceed with original value

    return since


def _step_audience(get_pref) -> Audience:
    """Guide the user through audience selection."""
    pref_idx = get_pref("audience", _AUDIENCE_CHOICES)
    default_idx = pref_idx if pref_idx is not None else 0  # Standard changelog
    return select_one(
        "👥 Target audience",
        _AUDIENCE_CHOICES,
        default_index=default_idx,
    )


def _step_format(get_pref) -> OutputFormat:
    """Guide the user through format selection."""
    pref_idx = get_pref("format", _FORMAT_CHOICES)
    default_idx = pref_idx if pref_idx is not None else 0
    return select_one(
        "📝 Output format",
        _FORMAT_CHOICES,
        default_index=default_idx,
    )


def _step_format_executive(_get_pref) -> str:
    """Guide executive user through format selection — PDF/DOCX preferred.

    Always defaults to PDF (index 0) since executive outputs are
    typically shared as polished documents.
    """
    return select_one(
        "📝 Output format",
        _FORMAT_CHOICES_EXECUTIVE,
        default_index=0,
        hint="For executive briefs, PDF or DOCX produce the most polished results.",
    )


def _step_format_narrative(_get_pref) -> str:
    """Guide narrative user through format selection — PDF/DOCX available."""
    return select_one(
        "📝 Output format",
        _FORMAT_CHOICES_NARRATIVE,
        default_index=0,
        hint="For narrative summaries, PDF or DOCX produce polished, shareable documents.",
    )


def _step_custom_title(repo_name: str) -> str:
    """Ask for an optional subtitle / custom release heading.

    The repository name is always used as the application name at the
    top of the document.  This step lets the user add a subtitle such
    as "Monthly Release Overview" or "Q1 Delivery Summary".
    """
    console.print()
    console.print("[bold]📝 Custom title / subtitle[/bold]")
    console.print(
        f"[dim]The repository name [bold]{repo_name}[/bold] will appear centered "
        "at the top of the document automatically.[/dim]",
    )
    console.print(
        "[dim]You can add an optional subtitle below it (e.g. a release type "
        "or summary heading).[/dim]",
    )
    console.print("[dim]Leave blank to skip.[/dim]")
    console.print()
    console.print("[dim]  Example document layout:[/dim]")
    console.print("[dim]    ┌──────────────────────────────────┐[/dim]")
    console.print(f"[dim]    │         [bold]{repo_name[:14]:<14s}[/bold]           │[/dim]")
    console.print("[dim]    │    Monthly Release Overview       │[/dim]")
    console.print("[dim]    │    Version 2.0.0                  │[/dim]")
    console.print("[dim]    └──────────────────────────────────┘[/dim]")
    console.print()
    raw = text_prompt("Subtitle", default="")
    result = raw.strip()
    if len(result) > 200:
        console.print("[yellow]⚠ Subtitle trimmed to 200 characters.[/yellow]")
        result = result[:200]
    return result


def _step_language(get_pref) -> str:
    """Guide language selection."""
    pref_idx = get_pref("language", _LANGUAGE_CHOICES)
    default_idx = pref_idx if pref_idx is not None else 0
    return select_one(
        "🌐 Output language",
        _LANGUAGE_CHOICES,
        default_index=default_idx,
        hint="Structural labels (headings, sections) will be translated. "
        "Content translation requires the deep-translator package.",
    )


def _confirm_overwrite_or_rename(filename: str) -> str | None:
    """Check if file exists; ask to overwrite or choose a new name.

    Returns the final filename, or ``None`` if the user cancels.
    """
    path = Path(filename)
    while path.exists():
        console.print(
            f"[yellow]⚠ File '{path}' already exists.[/yellow]",
        )
        action = select_one(
            "What would you like to do?",
            [
                ("Overwrite the existing file", "overwrite"),
                ("Choose a different filename", "rename"),
                ("Cancel (do not save)", "cancel"),
            ],
            default_index=0,
        )
        if action == "overwrite":
            return str(path)
        if action == "cancel":
            return None
        # Rename: ask again
        filename = text_prompt("New filename", default=str(path))
        path = Path(filename)
    return str(path)


def _step_display_and_export(
    output: str,
    output_format: OutputFormat,
    audience: Audience | None = None,
) -> None:
    """Display the result and offer to save."""
    panel = Panel(
        Text(output),
        title="[bold]📋 Release Notes[/bold]",
        border_style="green",
    )
    console.print(panel)

    console.print()
    save = confirm("Save to a file?", default=True)

    if save:
        ext = {
            OutputFormat.MARKDOWN: ".md",
            OutputFormat.PLAINTEXT: ".txt",
            OutputFormat.JSON: ".json",
        }[output_format]

        # Audience-aware default filename
        name_map = {
            Audience.TECHNICAL: "TECHNICAL_NOTES",
            Audience.USER: "WHATS_NEW",
            Audience.SUMMARY: "RELEASE_SUMMARY",
            Audience.CHANGELOG: "CHANGELOG",
            Audience.CUSTOMER: "CUSTOMER_UPDATE",
        }
        base = name_map.get(audience, "RELEASE_NOTES") if audience else "RELEASE_NOTES"
        default_name = f"{base}{ext}"
        filename = text_prompt("Filename", default=default_name)
        final = _confirm_overwrite_or_rename(filename)
        if final is None:
            console.print("[dim]Save cancelled.[/dim]")
        else:
            Path(final).write_text(output, encoding="utf-8")
            console.print(f"[green]✓[/green] Saved to [bold]{final}[/bold]")

    console.print()
    console.print("[green]Done![/green] 🎉")


def _step_display_and_export_executive(brief, exec_format: str, language: str = "en", accent_color: str = "#FB6400") -> None:
    """Display and export an executive brief."""
    from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer

    md_output = ExecutiveMarkdownRenderer().render(brief, lang=language)
    panel = Panel(
        Text(md_output),
        title="[bold]📋 Executive Release Brief[/bold]",
        border_style="green",
    )
    console.print(panel)

    console.print()
    save = confirm("Save to a file?", default=True)

    if save:
        ext_map = {"pdf": ".pdf", "docx": ".docx", "markdown": ".md", "json": ".json"}
        ext = ext_map.get(exec_format, ".md")
        default_name = f"RELEASE_BRIEF{ext}"
        filename = text_prompt("Filename", default=default_name)
        final = _confirm_overwrite_or_rename(filename)

        if final is None:
            console.print("[dim]Save cancelled.[/dim]")
        else:
            with console.status("[bold cyan]Rendering and exporting document...[/bold cyan]"):
                if exec_format == "pdf":
                    from releasepilot.rendering.executive_pdf import ExecutivePdfRenderer
                    Path(final).write_bytes(
                        ExecutivePdfRenderer().render_bytes(brief, lang=language, accent_color=accent_color)
                    )
                elif exec_format == "docx":
                    from releasepilot.rendering.executive_docx import ExecutiveDocxRenderer
                    Path(final).write_bytes(
                        ExecutiveDocxRenderer().render_bytes(brief, lang=language, accent_color=accent_color)
                    )
                elif exec_format == "json":
                    Path(final).write_text(
                        ExecutiveMarkdownRenderer().render_json(brief), encoding="utf-8",
                    )
                else:
                    Path(final).write_text(md_output, encoding="utf-8")

            console.print(f"[green]✓[/green] Saved to [bold]{final}[/bold]")

    console.print()
    console.print("[green]Done![/green] 🎉")


def _step_display_and_export_narrative(
    brief, narr_format: str, language: str = "en", accent_color: str = "#FB6400",
) -> None:
    """Display and export a narrative brief."""
    from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer

    md_output = NarrativeMarkdownRenderer().render(brief, lang=language)
    title_label = "📋 Narrative Release Summary" if brief.mode == "narrative" else "📋 Customer Product Update"
    panel = Panel(
        Text(md_output),
        title=f"[bold]{title_label}[/bold]",
        border_style="green",
    )
    console.print(panel)

    console.print()
    save = confirm("Save to a file?", default=True)

    if save:
        ext_map = {"pdf": ".pdf", "docx": ".docx", "markdown": ".md", "plaintext": ".txt", "json": ".json"}
        ext = ext_map.get(narr_format, ".md")
        default_name = f"NARRATIVE_SUMMARY{ext}"
        filename = text_prompt("Filename", default=default_name)
        final = _confirm_overwrite_or_rename(filename)

        if final is None:
            console.print("[dim]Save cancelled.[/dim]")
        else:
            with console.status("[bold cyan]Rendering and exporting document...[/bold cyan]"):
                if narr_format == "pdf":
                    from releasepilot.rendering.narrative_pdf import NarrativePdfRenderer
                    Path(final).write_bytes(
                        NarrativePdfRenderer().render_bytes(brief, lang=language, accent_color=accent_color),
                    )
                elif narr_format == "docx":
                    from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer
                    Path(final).write_bytes(
                        NarrativeDocxRenderer().render_bytes(brief, lang=language, accent_color=accent_color),
                    )
                elif narr_format == "json":
                    Path(final).write_text(
                        NarrativeMarkdownRenderer().render_json(brief), encoding="utf-8",
                    )
                elif narr_format == "plaintext":
                    from releasepilot.rendering.narrative_plain import NarrativePlaintextRenderer
                    Path(final).write_text(
                        NarrativePlaintextRenderer().render(brief), encoding="utf-8",
                    )
                else:
                    Path(final).write_text(md_output, encoding="utf-8")

            console.print(f"[green]✓[/green] Saved to [bold]{final}[/bold]")

    console.print()
    console.print("[green]Done![/green] 🎉")


# ── Repository URL clone/cleanup ─────────────────────────────────────────


def _step_clone_repo(url: str) -> str | None:
    """Clone a remote repository to a temporary directory.

    Returns the path to the cloned repository, or None on failure.
    """
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
