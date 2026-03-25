"""GitHub source collector — implements SourceCollector protocol.

Collects change items from a remote GitHub repository via the REST API.
Bridges the ``GitHubClient`` into the pipeline's source abstraction.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from releasepilot.domain.models import ChangeItem, ReleaseRange, SourceReference
from releasepilot.sources.github import GitHubClient, GitHubCommit

logger = logging.getLogger("releasepilot.github_collector")


class GitHubCollectorError(Exception):
    """Raised when GitHub commit collection fails."""


class GitHubSourceCollector:
    """Collects ChangeItems from a remote GitHub repository.

    Implements the ``SourceCollector`` protocol.

    Usage::

        collector = GitHubSourceCollector(
            client=client,
            owner="polprog-tech",
            repo="ReleasePilot",
            app_label="ReleasePilot",
        )
        items = collector.collect(release_range)
    """

    def __init__(
        self,
        client: GitHubClient,
        owner: str,
        repo: str,
        *,
        app_label: str = "",
        branch: str = "",
    ) -> None:
        self._client = client
        self._owner = owner
        self._repo = repo
        self._app_label = app_label
        self._branch = branch

    def collect(self, release_range: ReleaseRange) -> list[ChangeItem]:
        """Collect commits for the given release range.

        Supports both ref-based ranges (from_ref..to_ref via compare API)
        and date-based ranges (since date via list_commits API).
        """
        if _is_date(release_range.from_ref):
            return self._collect_by_date(
                since=release_range.from_ref,
                branch=release_range.to_ref,
            )

        return self._collect_by_compare(
            from_ref=release_range.from_ref,
            to_ref=release_range.to_ref,
        )

    def collect_by_date(self, since: str, branch: str = "") -> list[ChangeItem]:
        """Collect commits since a given date."""
        return self._collect_by_date(since=since, branch=branch or self._branch)

    def _collect_by_compare(self, from_ref: str, to_ref: str) -> list[ChangeItem]:
        """Collect commits between two refs using the compare API."""
        from releasepilot.sources.github import GitHubError

        try:
            result = self._client.compare(self._owner, self._repo, from_ref, to_ref)
        except GitHubError as exc:
            raise GitHubCollectorError(
                f"Failed to compare {from_ref}..{to_ref} on {self._owner}/{self._repo}: {exc}"
            ) from exc

        commits = result.get("commits", [])
        items: list[ChangeItem] = []
        for c in commits:
            commit = GitHubCommit(
                sha=c.get("sha", ""),
                short_sha=c.get("sha", "")[:8],
                title=c.get("commit", {}).get("message", "").split("\n", 1)[0],
                message=c.get("commit", {}).get("message", ""),
                author_name=(
                    c.get("commit", {}).get("author", {}).get("name", "")
                    or (c.get("author", {}).get("login", "") if c.get("author") else "")
                ),
                authored_date=c.get("commit", {}).get("author", {}).get("date", ""),
                committed_date=c.get("commit", {}).get("committer", {}).get("date", ""),
            )
            items.append(self._to_change_item(commit))

        logger.info(
            "Collected %d commits from GitHub %s/%s (%s..%s)",
            len(items),
            self._owner,
            self._repo,
            from_ref,
            to_ref,
        )
        return items

    def _collect_by_date(self, since: str, branch: str = "") -> list[ChangeItem]:
        """Collect commits since a date, paginating through all results."""
        from releasepilot.sources.github import GitHubError

        all_commits: list[GitHubCommit] = []
        page = 1
        max_pages = 20

        try:
            while page <= max_pages:
                batch = self._client.list_commits(
                    self._owner,
                    self._repo,
                    sha=branch or self._branch,
                    since=since,
                    per_page=100,
                    page=page,
                )
                if not batch:
                    break
                all_commits.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
        except GitHubError as exc:
            raise GitHubCollectorError(
                f"Failed to list commits since {since} on {self._owner}/{self._repo}: {exc}"
            ) from exc

        items = [self._to_change_item(c) for c in all_commits]
        logger.info(
            "Collected %d commits from GitHub %s/%s (since %s)",
            len(items),
            self._owner,
            self._repo,
            since,
        )
        return items

    def _to_change_item(self, commit: GitHubCommit) -> ChangeItem:
        """Convert a GitHub commit to a ChangeItem."""
        subject = commit.title.strip()
        body = ""
        if commit.message:
            parts = commit.message.split("\n", 1)
            body = parts[1].strip() if len(parts) > 1 else ""

        full_message = f"{subject}\n\n{body}".strip() if body else subject
        timestamp = _parse_iso_date(commit.authored_date or commit.committed_date)
        item_id = hashlib.sha256(commit.sha.encode()).hexdigest()[:20]

        metadata: dict[str, str] = {}
        if self._app_label:
            metadata["app_label"] = self._app_label
        metadata["source_type"] = "github"

        return ChangeItem(
            id=item_id,
            title=subject,
            description=body,
            raw_message=full_message,
            source=SourceReference(commit_hash=commit.sha),
            authors=(commit.author_name,) if commit.author_name else (),
            timestamp=timestamp,
            metadata=metadata,
        )


def _is_date(ref: str) -> bool:
    """Check if a ref looks like an ISO date (YYYY-MM-DD)."""
    if len(ref) < 8:
        return False
    try:
        datetime.strptime(ref[:10], "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _parse_iso_date(date_str: str) -> datetime | None:
    """Parse an ISO 8601 date string."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, TypeError):
        return None
