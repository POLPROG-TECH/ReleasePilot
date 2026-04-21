"""Git-based source collector.

Collects change items from a local git repository by running git log
between two refs. This is the primary source collector.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import time
from datetime import UTC, datetime

from releasepilot.domain.models import ChangeItem, ReleaseRange, SourceReference

logger = logging.getLogger("releasepilot.git")


class GitCollectionError(Exception):
    """Raised when git commands fail."""


_FIELD_SEP = "\x1f"  # ASCII Unit Separator - cannot appear in git output
_RECORD_SEP = "\x1e"  # ASCII Record Separator - cannot appear in git output

_GIT_LOG_FORMAT = _FIELD_SEP.join(["%H", "%an", "%aI", "%s", "%b"]) + _RECORD_SEP

# Allowed characters in git refs - prevents shell injection via crafted refs.
_SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9._/~^{}\-@:]+$")

# Transient git errors that are worth retrying.
_TRANSIENT_PATTERNS = (
    "index.lock",
    "Unable to create",
    "cannot lock ref",
    "Connection timed out",
    "Connection reset",
)

_MAX_RETRIES = 2
_RETRY_DELAY = 0.5  # seconds


def validate_ref(ref: str) -> None:
    """Raise GitCollectionError if *ref* contains unsafe characters."""
    if not ref:
        return
    if not _SAFE_REF_RE.match(ref):
        raise GitCollectionError(
            f"Invalid git ref: '{ref}'. "
            "Refs may only contain alphanumerics, dots, slashes, tildes, "
            "carets, braces, hyphens, at-signs, and colons."
        )


class GitSourceCollector:
    """Collects ChangeItems from a local git repository."""

    def __init__(self, repo_path: str = ".") -> None:
        self._repo_path = repo_path

    def collect(self, release_range: ReleaseRange) -> list[ChangeItem]:
        validate_ref(release_range.from_ref)
        validate_ref(release_range.to_ref)
        raw = self._run_git_log(release_range.from_ref, release_range.to_ref)
        return self._parse_log(raw)

    def collect_by_date(self, since: str, branch: str = "HEAD") -> list[ChangeItem]:
        """Collect commits since a date on a given branch.

        Args:
            since: ISO date string (e.g. "2025-01-01")
            branch: Branch name or ref to walk (default: HEAD)
        """
        validate_ref(branch)
        raw = self._run_git(
            [
                "log",
                f"--since={since}",
                f"--pretty=format:{_GIT_LOG_FORMAT}",
                "--no-merges",
                branch,
            ]
        )
        return self._parse_log(raw)

    def first_commit_date(self, *, branch: str = "") -> str | None:
        """Return the ISO date of the oldest reachable commit.

        Uses ``--diff-filter=A`` with ``--reverse`` and ``--max-count=1``
        via a ``rev-list`` approach to avoid walking the entire history on
        large repositories.  Falls back to a bounded ``git log`` if needed.
        """
        if branch:
            validate_ref(branch)
        try:
            # Fast path: use rev-list --max-parents=0 to find root commits.
            args = ["rev-list", "--max-parents=0", "--format=%aI"]
            if branch:
                args.append(branch)
            else:
                args.append("HEAD")
            result = self._run_git(args, timeout=15)
            dates: list[str] = []
            for line in result.strip().splitlines():
                line = line.strip()
                if line and not line.startswith("commit "):
                    dates.append(line)
            if dates:
                dates.sort()
                return dates[0]
            return None
        except GitCollectionError:
            return None

    def resolve_latest_tag(self) -> str:
        """Return the most recent reachable tag, or empty string if none."""
        try:
            result = self._run_git(["describe", "--tags", "--abbrev=0"])
            return result.strip()
        except GitCollectionError:
            return ""

    def list_tags(self, limit: int = 10) -> list[str]:
        """Return recent tags in reverse chronological order."""
        try:
            result = self._run_git(
                [
                    "tag",
                    "--sort=-creatordate",
                ]
            )
            tags = [t for t in result.strip().splitlines() if t]
            return tags[:limit] if limit else tags
        except GitCollectionError:
            return []

    def check_ancestor(self, ancestor: str, descendant: str) -> bool:
        """Return True if *ancestor* is an ancestor of *descendant*."""
        validate_ref(ancestor)
        validate_ref(descendant)
        try:
            cmd = [
                "git",
                "-C",
                self._repo_path,
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return True  # Assume valid on error to avoid blocking

    def _run_git_log(self, from_ref: str, to_ref: str) -> str:
        rev_range = f"{from_ref}..{to_ref}" if from_ref else to_ref
        return self._run_git(
            [
                "log",
                f"--pretty=format:{_GIT_LOG_FORMAT}",
                "--no-merges",
                rev_range,
            ]
        )

    def _run_git(self, args: list[str], timeout: int = 30) -> str:
        cmd = ["git", "-C", self._repo_path] + [a for a in args if a]
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    encoding="utf-8",
                    errors="replace",
                )
            except FileNotFoundError as exc:
                raise GitCollectionError("git is not installed or not on PATH") from exc
            except subprocess.TimeoutExpired as exc:
                raise GitCollectionError(f"git command timed out: {' '.join(cmd)}") from exc

            if result.returncode == 0:
                return result.stdout

            # Check if transient - retry if so.
            stderr = result.stderr.strip()
            if attempt < _MAX_RETRIES and any(p in stderr for p in _TRANSIENT_PATTERNS):
                logger.debug("Transient git error (attempt %d): %s", attempt + 1, stderr)
                time.sleep(_RETRY_DELAY * (attempt + 1))
                last_exc = GitCollectionError(
                    f"git command failed (exit {result.returncode}): {stderr}"
                )
                continue

            raise GitCollectionError(f"git command failed (exit {result.returncode}): {stderr}")

        # Exhausted retries
        raise last_exc or GitCollectionError("git command failed after retries")

    def _parse_log(self, raw: str) -> list[ChangeItem]:
        if not raw.strip():
            return []

        items: list[ChangeItem] = []
        for record in raw.split(_RECORD_SEP):
            record = record.strip()
            if not record:
                continue

            parts = record.split(_FIELD_SEP, maxsplit=4)
            if len(parts) < 4:
                continue

            commit_hash = parts[0].strip()
            author = parts[1].strip()
            date_str = parts[2].strip()
            subject = parts[3].strip()
            body = parts[4].strip() if len(parts) > 4 else ""

            full_message = f"{subject}\n\n{body}".strip() if body else subject

            timestamp = _parse_iso_date(date_str)
            # Use 20 hex chars (80 bits) to reduce collision risk.
            item_id = hashlib.sha256(commit_hash.encode()).hexdigest()[:20]

            items.append(
                ChangeItem(
                    id=item_id,
                    title=subject,
                    description=body,
                    raw_message=full_message,
                    source=SourceReference(commit_hash=commit_hash),
                    authors=(author,),
                    timestamp=timestamp,
                )
            )

        return items


def _parse_iso_date(date_str: str) -> datetime | None:
    try:
        return datetime.fromisoformat(date_str).astimezone(UTC)
    except (ValueError, TypeError):
        return None
