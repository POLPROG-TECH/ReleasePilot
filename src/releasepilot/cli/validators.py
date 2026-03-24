"""Pre-flight validation for ReleasePilot CLI commands.

Validates inputs before expensive pipeline operations. Returns UserError
instances when validation fails, allowing the CLI to display structured
error messages rather than raw exceptions.
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

from releasepilot.cli.errors import (
    UserError,
    export_path_error,
    invalid_date,
    not_a_git_repo,
    ref_not_found,
    source_file_not_found,
)
from releasepilot.config.settings import Settings
from releasepilot.sources.git import GitCollectionError, validate_ref


def validate_settings(settings: Settings) -> UserError | None:
    """Run all applicable validations on the settings.

    Returns None if valid, or a UserError describing the first problem found.
    """
    # Source file mode
    if settings.is_file_source:
        return _validate_source_file(settings.source_file)

    # Git-based mode: check repo first
    err = _validate_git_repo(settings.repo_path)
    if err:
        return err

    # Sanitize refs early to prevent command injection.
    for ref_label, ref_value in [
        ("from_ref", settings.from_ref),
        ("to_ref", settings.to_ref),
        ("branch", settings.branch),
    ]:
        if ref_value:
            try:
                validate_ref(ref_value)
            except GitCollectionError as exc:
                return UserError(
                    summary=f"Invalid {ref_label}: '{ref_value}'",
                    reason=str(exc),
                    suggestions=["Use a valid git ref (tag, branch, or commit hash)"],
                )

    # Date-range mode
    if settings.is_date_range:
        err = _validate_date(settings.since_date)
        if err:
            return err
        if settings.branch:
            err = _validate_ref(settings.repo_path, settings.branch)
            if err:
                return err
        return None

    # Ref-range mode
    if settings.from_ref:
        err = _validate_ref(settings.repo_path, settings.from_ref)
        if err:
            return err

    if settings.to_ref and settings.to_ref != "HEAD":
        err = _validate_ref(settings.repo_path, settings.to_ref)
        if err:
            return err

    # Ancestor check: if both refs are set, verify from_ref is reachable from to_ref.
    if settings.from_ref and settings.to_ref:
        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(settings.repo_path)
        if not collector.check_ancestor(settings.from_ref, settings.to_ref):
            return UserError(
                summary=f"'{settings.from_ref}' is not an ancestor of '{settings.to_ref}'",
                reason="The starting ref is not reachable from the ending ref, "
                "which would produce an empty or misleading diff.",
                suggestions=[
                    "Swap --from and --to if the order is reversed",
                    "Verify the tags/branches belong to the same lineage",
                    "Use 'git log --oneline --graph' to visualize history",
                ],
            )

    return None


def validate_export_path(path: str, *, allow_overwrite: bool = False) -> UserError | None:
    """Validate that the export output path is writable.

    Returns None if valid, or a UserError describing the problem.
    """
    out = Path(path)

    # Check parent directory exists
    parent = out.parent
    if not parent.exists():
        return export_path_error(
            path,
            f"The directory '{parent}' does not exist.",
        )

    # Check parent is writable
    if not _is_writable(parent):
        return export_path_error(
            path,
            f"No write permission for directory '{parent}'.",
        )

    # Check for existing file
    if out.exists() and not allow_overwrite:
        return UserError(
            summary=f"File already exists: '{path}'",
            reason="The output file already exists and would be overwritten.",
            suggestions=[
                "Use a different output path",
                "Delete the existing file first",
                "The file will be overwritten if you confirm",
            ],
        )

    return None


def validate_export_format_deps(fmt: str) -> UserError | None:
    """Check that required dependencies for the given format are installed."""
    if fmt == "pdf":
        try:
            import reportlab  # noqa: F401
        except ImportError:
            from releasepilot.cli.errors import missing_export_format_deps

            return missing_export_format_deps("PDF")

    if fmt == "docx":
        try:
            import docx  # noqa: F401
        except ImportError:
            from releasepilot.cli.errors import missing_export_format_deps

            return missing_export_format_deps("DOCX")

    return None


# ── Internal helpers ─────────────────────────────────────────────────────


def _validate_git_repo(repo_path: str) -> UserError | None:
    """Check that the path is a valid git repository."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return not_a_git_repo(repo_path)
    except FileNotFoundError:
        return UserError(
            summary="Git is not installed",
            reason="The 'git' command was not found on your system.",
            suggestions=[
                "Install git: https://git-scm.com/downloads",
                "Use --source-file to generate from a JSON file instead",
            ],
        )
    except subprocess.TimeoutExpired:
        return UserError(
            summary="Git command timed out",
            reason=f"Could not verify the repository at '{repo_path}' within 10 seconds.",
            suggestions=["Check that the repository is accessible and not on a slow network mount"],
        )
    return None


def _validate_ref(repo_path: str, ref: str) -> UserError | None:
    """Check that a git ref (tag, branch, commit) exists."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--verify", f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            # Try without ^{commit} in case it's a different kind of ref
            result2 = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "--verify", ref],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result2.returncode != 0:
                return ref_not_found(ref, _classify_ref(ref))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # git issues already caught by _validate_git_repo
    return None


def _validate_date(date_str: str) -> UserError | None:
    """Validate an ISO date string."""
    try:
        date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return invalid_date(date_str)
    return None


def _validate_source_file(path: str) -> UserError | None:
    """Check that the source file exists and is readable."""
    p = Path(path)
    if not p.exists():
        return source_file_not_found(path)
    if not p.is_file():
        return UserError(
            summary=f"Not a file: '{path}'",
            reason="The --source-file path must point to a regular file, not a directory.",
        )
    return None


def _classify_ref(ref: str) -> str:
    """Guess what kind of ref the user intended."""
    if re.match(r"^v?\d+\.\d+", ref):
        return "tag"
    if ref in ("main", "master", "develop", "HEAD"):
        return "branch"
    if re.match(r"^[0-9a-f]{7,40}$", ref):
        return "commit"
    return "ref"


def _is_writable(path: Path) -> bool:
    """Check if a path is writable."""
    import os

    return os.access(path, os.W_OK)
