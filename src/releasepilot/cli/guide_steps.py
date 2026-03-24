"""Step implementations for the guided interactive workflow.

Individual step functions used by the main guide workflow in ``guide.py``.
Each function handles one discrete step of the guided release-notes wizard
(repo inspection, branch selection, time-range, audience/format selection,
display and export, etc.).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from releasepilot.cli.prompts import confirm, select_one, text_prompt
from releasepilot.domain.enums import Audience, OutputFormat
from releasepilot.sources.inspector import RepoInspection, inspect_repo

console = Console(stderr=True)

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
            f"   → Effective: since [cyan]{effective}[/cyan] (adjusted to first available commit)",
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


def _step_display_and_export_executive(
    brief, exec_format: str, language: str = "en", accent_color: str = "#FB6400"
) -> None:
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
                        ExecutivePdfRenderer().render_bytes(
                            brief, lang=language, accent_color=accent_color
                        )
                    )
                elif exec_format == "docx":
                    from releasepilot.rendering.executive_docx import ExecutiveDocxRenderer

                    Path(final).write_bytes(
                        ExecutiveDocxRenderer().render_bytes(
                            brief, lang=language, accent_color=accent_color
                        )
                    )
                elif exec_format == "json":
                    Path(final).write_text(
                        ExecutiveMarkdownRenderer().render_json(brief),
                        encoding="utf-8",
                    )
                else:
                    Path(final).write_text(md_output, encoding="utf-8")

            console.print(f"[green]✓[/green] Saved to [bold]{final}[/bold]")

    console.print()
    console.print("[green]Done![/green] 🎉")


def _step_display_and_export_narrative(
    brief,
    narr_format: str,
    language: str = "en",
    accent_color: str = "#FB6400",
) -> None:
    """Display and export a narrative brief."""
    from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer

    md_output = NarrativeMarkdownRenderer().render(brief, lang=language)
    title_label = (
        "📋 Narrative Release Summary"
        if brief.mode == "narrative"
        else "📋 Customer Product Update"
    )
    panel = Panel(
        Text(md_output),
        title=f"[bold]{title_label}[/bold]",
        border_style="green",
    )
    console.print(panel)

    console.print()
    save = confirm("Save to a file?", default=True)

    if save:
        ext_map = {
            "pdf": ".pdf",
            "docx": ".docx",
            "markdown": ".md",
            "plaintext": ".txt",
            "json": ".json",
        }
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
                        NarrativePdfRenderer().render_bytes(
                            brief, lang=language, accent_color=accent_color
                        ),
                    )
                elif narr_format == "docx":
                    from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer

                    Path(final).write_bytes(
                        NarrativeDocxRenderer().render_bytes(
                            brief, lang=language, accent_color=accent_color
                        ),
                    )
                elif narr_format == "json":
                    Path(final).write_text(
                        NarrativeMarkdownRenderer().render_json(brief),
                        encoding="utf-8",
                    )
                elif narr_format == "plaintext":
                    from releasepilot.rendering.narrative_plain import NarrativePlaintextRenderer

                    Path(final).write_text(
                        NarrativePlaintextRenderer().render(brief),
                        encoding="utf-8",
                    )
                else:
                    Path(final).write_text(md_output, encoding="utf-8")

            console.print(f"[green]✓[/green] Saved to [bold]{final}[/bold]")

    console.print()
    console.print("[green]Done![/green] 🎉")
