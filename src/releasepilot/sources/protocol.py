"""Source collector protocol.

Every source collector must implement this protocol.
This is the extension point for adding GitHub, GitLab, Jira, etc.
"""

from __future__ import annotations

from typing import Protocol

from releasepilot.domain.models import ChangeItem, ReleaseRange


class SourceCollector(Protocol):
    """Collects raw change data from a source and normalizes it to ChangeItems."""

    def collect(self, release_range: ReleaseRange) -> list[ChangeItem]:
        """Collect changes for the given release range.

        Returns a list of ChangeItem instances with at minimum:
        - id (unique within this collection)
        - title (first line of commit / PR title)
        - raw_message (full original message)
        - source (provenance reference)
        - timestamp
        - authors
        """
        ...
