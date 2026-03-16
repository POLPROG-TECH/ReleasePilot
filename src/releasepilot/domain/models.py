"""Domain models for ReleasePilot.

These are the core data structures that flow through the pipeline.
All models are frozen dataclasses for immutability and hashability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from releasepilot.domain.enums import ChangeCategory, Importance


@dataclass(frozen=True)
class SourceReference:
    """Provenance information linking a change back to its origin."""

    commit_hash: str = ""
    pr_number: int | None = None
    issue_numbers: tuple[int, ...] = ()
    url: str = ""

    @property
    def short_hash(self) -> str:
        return self.commit_hash[:8] if self.commit_hash else ""


@dataclass(frozen=True)
class ChangeItem:
    """A single normalized change in the release.

    This is the central domain object. Every source collector produces these,
    and every downstream stage consumes them.
    """

    id: str
    title: str
    description: str = ""
    category: ChangeCategory = ChangeCategory.OTHER
    scope: str = ""
    importance: Importance = Importance.NORMAL
    is_breaking: bool = False
    source: SourceReference = field(default_factory=SourceReference)
    authors: tuple[str, ...] = ()
    timestamp: datetime | None = None
    raw_message: str = ""
    metadata: dict[str, str] = field(default_factory=dict, hash=False)

    @property
    def sort_key(self) -> tuple[int, str, str]:
        """Deterministic sort: category order → scope → title."""
        return (self.category.sort_order, self.scope.lower(), self.title.lower())


@dataclass(frozen=True)
class ReleaseRange:
    """Defines the scope of changes in a release."""

    from_ref: str
    to_ref: str
    version: str = ""
    title: str = ""
    app_name: str = ""
    release_date: date | None = None

    @property
    def display_title(self) -> str:
        """Full title for plain-text contexts (includes app name if set)."""
        parts: list[str] = []
        if self.app_name:
            parts.append(self.app_name)
        if self.title:
            parts.append(self.title)
        elif self.version:
            parts.append(f"Release {self.version}")
        else:
            parts.append(f"{self.from_ref}..{self.to_ref}")
        return " — ".join(parts)

    @property
    def subtitle(self) -> str:
        """Title portion without the app name (for structured layouts)."""
        if self.title:
            return self.title
        if self.version:
            return f"Release {self.version}"
        return f"{self.from_ref}..{self.to_ref}"


@dataclass(frozen=True)
class ChangeGroup:
    """A group of change items under one category."""

    category: ChangeCategory
    items: tuple[ChangeItem, ...]

    @property
    def sort_key(self) -> int:
        return self.category.sort_order

    @property
    def display_label(self) -> str:
        return self.category.display_label


@dataclass(frozen=True)
class ReleaseNotes:
    """Fully composed release notes, ready for rendering.

    This is the output of the pipeline orchestrator and the input to renderers.
    """

    release_range: ReleaseRange
    groups: tuple[ChangeGroup, ...]
    highlights: tuple[ChangeItem, ...] = ()
    breaking_changes: tuple[ChangeItem, ...] = ()
    total_changes: int = 0
    metadata: dict[str, str] = field(default_factory=dict, hash=False)

    @property
    def is_empty(self) -> bool:
        return self.total_changes == 0
