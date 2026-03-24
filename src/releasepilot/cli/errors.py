"""User-facing error display for ReleasePilot CLI.

Provides structured, actionable error messages that guide the user
toward fixing the problem rather than showing raw technical errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console(stderr=True)


@dataclass
class UserError:
    """A structured, user-friendly error with context and suggested fixes.

    Designed to be raised/displayed at the CLI boundary. Core domain code
    should raise domain exceptions; the CLI layer wraps them into UserErrors.
    """

    summary: str
    reason: str = ""
    suggestions: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    hint: str = ""

    def display(self) -> None:
        """Render this error to stderr with Rich formatting."""
        parts: list[str] = []

        parts.append(f"[bold red]✗ {self.summary}[/bold red]")

        if self.reason:
            parts.append(f"\n[dim]Reason:[/dim] {self.reason}")

        if self.suggestions:
            parts.append("\n[bold]What you can do:[/bold]")
            for suggestion in self.suggestions:
                parts.append(f"  → {suggestion}")

        if self.commands:
            parts.append("\n[bold]Example commands:[/bold]")
            for cmd in self.commands:
                parts.append(f"  [cyan]$ {cmd}[/cyan]")

        if self.hint:
            parts.append(f"\n[dim]💡 {self.hint}[/dim]")

        console.print(
            Panel(
                Text.from_markup("\n".join(parts)),
                border_style="red",
                padding=(1, 2),
            )
        )

    def exit(self, code: int = 1) -> None:
        """Display the error and exit."""
        self.display()
        raise SystemExit(code)


# ── Factory functions for common error scenarios ─────────────────────────


def not_a_git_repo(path: str) -> UserError:
    return UserError(
        summary="Not a git repository",
        reason=f"The path '{path}' is not inside a git repository.",
        suggestions=[
            "Make sure you are in the correct directory",
            "Use --repo to point to a git repository",
            "Use --source-file to generate from a JSON file instead",
        ],
        commands=[
            "releasepilot generate --repo /path/to/your/repo --version 1.0.0",
            "releasepilot generate --source-file changes.json --version 1.0.0",
        ],
    )


def ref_not_found(ref: str, ref_type: str = "ref") -> UserError:
    return UserError(
        summary=f"Git {ref_type} not found: '{ref}'",
        reason=f"The {ref_type} '{ref}' does not exist in this repository.",
        suggestions=[
            f"Check that '{ref}' is a valid tag, branch, or commit hash",
            "List available tags with: git tag --list",
            "List available branches with: git branch --all",
        ],
        commands=[
            "releasepilot generate --from v1.0.0 --to v1.1.0",
            "releasepilot generate --since 2025-01-01 --branch main",
        ],
    )


def no_tags_found(repo_path: str) -> UserError:
    return UserError(
        summary="No tags found in repository",
        reason=(
            "ReleasePilot tried to auto-detect the release range from tags, but no tags were found."
        ),
        suggestions=[
            "Use --from and --to to specify the commit range explicitly",
            "Use --since and --branch for date-based generation",
            "Use 'releasepilot guide' for an interactive workflow",
            "Use --source-file to generate from a JSON file",
        ],
        commands=[
            "releasepilot generate --from <commit> --to HEAD --version 1.0.0",
            "releasepilot generate --since 2025-01-01 --branch main",
            "releasepilot guide",
        ],
        hint="Tags are required for automatic range detection. Create tags with: git tag v1.0.0",
    )


def empty_range(from_ref: str, to_ref: str) -> UserError:
    return UserError(
        summary="No changes found in range",
        reason=f"The range '{from_ref}..{to_ref}' contains no commits.",
        suggestions=[
            "Verify that the range is correct and not reversed",
            "Check if there are commits between these refs",
            "Try a wider range or different refs",
        ],
        commands=[
            f"git log --oneline {from_ref}..{to_ref}",
            "releasepilot generate --since 2025-01-01 --branch main",
        ],
    )


def invalid_date(date_str: str) -> UserError:
    return UserError(
        summary=f"Invalid date format: '{date_str}'",
        reason="The --since option expects a date in YYYY-MM-DD format.",
        suggestions=[
            "Use ISO 8601 date format: YYYY-MM-DD",
        ],
        commands=[
            "releasepilot generate --since 2025-01-15 --branch main",
        ],
    )


def source_file_not_found(path: str) -> UserError:
    return UserError(
        summary=f"Source file not found: '{path}'",
        reason=f"The file '{path}' does not exist or is not readable.",
        suggestions=[
            "Check the file path and try again",
            "Use a relative or absolute path to the JSON file",
        ],
        commands=[
            "releasepilot generate --source-file ./changes.json --version 1.0.0",
        ],
    )


def export_path_error(path: str, reason: str) -> UserError:
    return UserError(
        summary=f"Cannot write to: '{path}'",
        reason=reason,
        suggestions=[
            "Check that the output directory exists",
            "Check file permissions",
            "Use a different output path",
        ],
        commands=[
            "releasepilot export --source-file changes.json -o ./output/RELEASE.md",
        ],
    )


def git_command_failed(stderr: str) -> UserError:
    """Wrap a raw git error into a user-friendly message."""
    # Classify common git errors
    lower = stderr.lower()

    if "unknown revision" in lower or "ambiguous argument" in lower:
        # Extract the problematic ref from the error
        ref = _extract_ref_from_git_error(stderr)
        return ref_not_found(ref, "revision")

    if "not a git repository" in lower:
        return not_a_git_repo(".")

    if "bad default revision" in lower:
        return UserError(
            summary="Repository has no commits",
            reason="The repository exists but has no commit history yet.",
            suggestions=[
                "Make at least one commit before generating release notes",
                "Use --source-file to generate from a JSON file instead",
            ],
        )

    # Fallback: wrap the raw error
    return UserError(
        summary="Git operation failed",
        reason=stderr.strip(),
        suggestions=[
            "Check that git is installed and the repository is valid",
            "Try running the git command manually to see more detail",
        ],
        hint="Run with a wider range or use 'releasepilot guide' for assistance.",
    )


def missing_export_format_deps(fmt: str) -> UserError:
    return UserError(
        summary=f"Missing dependencies for {fmt} export",
        reason=f"The {fmt} format requires additional packages that are not installed.",
        suggestions=[
            "Install the export dependencies with pip",
        ],
        commands=[
            'python3 -m pip install "releasepilot[export]"',
            f"python3 -m pip install {'reportlab' if fmt == 'pdf' else 'python-docx'}",
        ],
    )


def _extract_ref_from_git_error(stderr: str) -> str:
    """Try to extract the problematic ref from a git error message."""
    # Pattern: "ambiguous argument 'v1.0.0..v1.1.0'"
    import re

    match = re.search(r"'([^']+)'", stderr)
    return match.group(1) if match else "unknown"
