"""Repository inspector.

Inspects a local git repository to gather metadata useful for guided workflows:
- Default/available branches
- Existing changelog or release notes files
- Recent tags
- Repository validity

This module is pure infrastructure — it reads from the repo but does not
modify it or participate in the pipeline data flow.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class InspectionError(Exception):
    """Raised when repository inspection fails."""


# Files commonly used for changelogs / release notes (case-insensitive search)
_CHANGELOG_PATTERNS: tuple[str, ...] = (
    "CHANGELOG.md",
    "CHANGELOG.rst",
    "CHANGELOG.txt",
    "CHANGELOG",
    "changelog.md",
    "CHANGES.md",
    "CHANGES.rst",
    "CHANGES",
    "HISTORY.md",
    "HISTORY.rst",
    "RELEASE_NOTES.md",
    "RELEASE-NOTES.md",
    "release_notes.md",
    "RELEASES.md",
    "NEWS.md",
    "NEWS",
    "docs/changelog.md",
    "docs/CHANGELOG.md",
    "docs/release-notes.md",
    "docs/releases.md",
    ".changelog/",
)

# Branch names to try as default, in priority order
_DEFAULT_BRANCH_CANDIDATES: tuple[str, ...] = ("main", "master", "develop")


@dataclass(frozen=True)
class RepoInspection:
    """Result of inspecting a repository."""

    path: str
    is_valid_repo: bool
    branches: tuple[str, ...] = ()
    default_branch: str = ""
    current_branch: str = ""
    changelog_files: tuple[str, ...] = ()
    recent_tags: tuple[str, ...] = ()
    has_commits: bool = False
    error: str = ""


def inspect_repo(repo_path: str) -> RepoInspection:
    """Inspect a local git repository and return structured metadata.

    This never raises — it returns an inspection result with is_valid_repo=False
    and an error message if the repo cannot be inspected.
    """
    path = Path(repo_path).resolve()

    if not path.exists():
        return RepoInspection(
            path=str(path),
            is_valid_repo=False,
            error=f"Path does not exist: {path}",
        )

    # Verify it's a git repo
    if not _is_git_repo(str(path)):
        return RepoInspection(
            path=str(path),
            is_valid_repo=False,
            error=f"Not a git repository: {path}",
        )

    branches = _list_branches(str(path))
    current_branch = _get_current_branch(str(path))
    default_branch = _detect_default_branch(str(path), branches)
    changelog_files = _find_changelog_files(path)
    recent_tags = _list_recent_tags(str(path))
    has_commits = _has_commits(str(path))

    return RepoInspection(
        path=str(path),
        is_valid_repo=True,
        branches=tuple(branches),
        default_branch=default_branch,
        current_branch=current_branch,
        changelog_files=tuple(changelog_files),
        recent_tags=tuple(recent_tags),
        has_commits=has_commits,
    )


def _is_git_repo(repo_path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _list_branches(repo_path: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "branch", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return []
        return [b.strip() for b in result.stdout.strip().splitlines() if b.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _get_current_branch(repo_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _detect_default_branch(repo_path: str, branches: list[str]) -> str:
    """Detect the default branch.

    Strategy:
    1. Check remote HEAD (most reliable)
    2. Fall back to well-known branch names in priority order
    3. Fall back to current branch
    """
    # Try remote HEAD
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            ref = result.stdout.strip()
            # refs/remotes/origin/main → main
            branch = ref.split("/")[-1]
            if branch in branches:
                return branch
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fall back to well-known names
    for candidate in _DEFAULT_BRANCH_CANDIDATES:
        if candidate in branches:
            return candidate

    # Fall back to first branch
    return branches[0] if branches else ""


def _find_changelog_files(repo_path: Path) -> list[str]:
    """Find changelog/release-note files in the repository."""
    found: list[str] = []

    for pattern in _CHANGELOG_PATTERNS:
        candidate = repo_path / pattern
        if pattern.endswith("/"):
            if candidate.is_dir():
                found.append(pattern)
        elif candidate.exists():
            found.append(pattern)

    return sorted(found)


def _list_recent_tags(repo_path: str, limit: int = 10) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "tag", "--sort=-creatordate"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return []
        tags = [t.strip() for t in result.stdout.strip().splitlines() if t.strip()]
        return tags[:limit]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _has_commits(repo_path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
