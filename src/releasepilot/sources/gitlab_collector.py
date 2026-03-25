"""GitLab source collector — implements SourceCollector protocol.

Collects change items from a remote GitLab repository via the API.
Bridges the existing ``GitLabClient`` into the pipeline's source abstraction.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from releasepilot.domain.models import ChangeItem, ReleaseRange, SourceReference
from releasepilot.sources.gitlab import GitLabClient, GitLabCommit

logger = logging.getLogger("releasepilot.gitlab_collector")


class GitLabCollectorError(Exception):
    """Raised when GitLab commit collection fails."""


class GitLabSourceCollector:
    """Collects ChangeItems from a remote GitLab repository.

    Implements the ``SourceCollector`` protocol.

    Usage::

        collector = GitLabSourceCollector(
            client=client,
            project_id=123,
            app_label="MyService",
        )
        items = collector.collect(release_range)
    """

    def __init__(
        self,
        client: GitLabClient,
        project_id: int,
        *,
        app_label: str = "",
        branch: str = "",
    ) -> None:
        self._client = client
        self._project_id = project_id
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
        from releasepilot.sources.gitlab import GitLabError

        try:
            result = self._client.compare(self._project_id, from_ref, to_ref)
        except GitLabError as exc:
            raise GitLabCollectorError(
                f"Failed to compare {from_ref}..{to_ref} on project {self._project_id}: {exc}"
            ) from exc

        commits = result.get("commits", [])
        items: list[ChangeItem] = []
        for c in commits:
            commit = GitLabCommit(
                sha=c.get("id", ""),
                short_id=c.get("short_id", c.get("id", "")[:8]),
                title=c.get("title", ""),
                message=c.get("message", ""),
                author_name=c.get("author_name", ""),
                authored_date=c.get("authored_date", ""),
                committed_date=c.get("committed_date", ""),
            )
            items.append(self._to_change_item(commit))

        logger.info(
            "Collected %d commits from GitLab project %d (%s..%s)",
            len(items),
            self._project_id,
            from_ref,
            to_ref,
        )
        return items

    def _collect_by_date(self, since: str, branch: str = "") -> list[ChangeItem]:
        """Collect commits since a date, paginating through all results."""
        from releasepilot.sources.gitlab import GitLabError

        all_commits: list[GitLabCommit] = []
        page = 1
        max_pages = 20  # Safety limit

        try:
            while page <= max_pages:
                batch = self._client.list_commits(
                    self._project_id,
                    ref=branch or self._branch,
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
        except GitLabError as exc:
            raise GitLabCollectorError(
                f"Failed to list commits since {since} on project {self._project_id}: {exc}"
            ) from exc

        items = [self._to_change_item(c) for c in all_commits]
        logger.info(
            "Collected %d commits from GitLab project %d (since %s)",
            len(items),
            self._project_id,
            since,
        )
        return items

    def _to_change_item(self, commit: GitLabCommit) -> ChangeItem:
        """Convert a GitLab commit to a ChangeItem."""
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
        metadata["source_type"] = "gitlab"

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
