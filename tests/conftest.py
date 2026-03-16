"""Shared test fixtures for ReleasePilot tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from releasepilot.config.settings import FilterConfig, RenderConfig
from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import (
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)


@pytest.fixture()
def sample_range() -> ReleaseRange:
    return ReleaseRange(
        from_ref="v1.0.0",
        to_ref="v1.1.0",
        version="1.1.0",
        title="Release 1.1.0",
    )


@pytest.fixture()
def sample_source_ref() -> SourceReference:
    return SourceReference(
        commit_hash="abc123def456",
        pr_number=42,
        issue_numbers=(10, 11),
    )


@pytest.fixture()
def sample_items() -> list[ChangeItem]:
    ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
    return [
        ChangeItem(
            id="item-1",
            title="Add user authentication",
            description="JWT-based auth system",
            category=ChangeCategory.FEATURE,
            scope="auth",
            importance=Importance.HIGH,
            source=SourceReference(commit_hash="aaa111", pr_number=10),
            authors=("alice",),
            timestamp=ts,
            raw_message="feat(auth): Add user authentication",
        ),
        ChangeItem(
            id="item-2",
            title="Fix login redirect loop",
            category=ChangeCategory.BUGFIX,
            scope="auth",
            source=SourceReference(commit_hash="bbb222"),
            authors=("bob",),
            timestamp=ts,
            raw_message="fix(auth): Fix login redirect loop",
        ),
        ChangeItem(
            id="item-3",
            title="Improve dashboard loading speed",
            category=ChangeCategory.PERFORMANCE,
            scope="dashboard",
            source=SourceReference(commit_hash="ccc333"),
            authors=("charlie",),
            timestamp=ts,
            raw_message="perf(dashboard): Improve dashboard loading speed",
        ),
        ChangeItem(
            id="item-4",
            title="Remove legacy API endpoints",
            category=ChangeCategory.BREAKING,
            scope="api",
            importance=Importance.HIGH,
            is_breaking=True,
            source=SourceReference(commit_hash="ddd444"),
            authors=("alice",),
            timestamp=ts,
            raw_message="feat(api)!: Remove legacy API endpoints",
        ),
        ChangeItem(
            id="item-5",
            title="Update CI pipeline",
            category=ChangeCategory.INFRASTRUCTURE,
            source=SourceReference(commit_hash="eee555"),
            authors=("bob",),
            timestamp=ts,
            raw_message="ci: Update CI pipeline",
        ),
        ChangeItem(
            id="item-6",
            title="Refactor database layer",
            category=ChangeCategory.REFACTOR,
            scope="db",
            source=SourceReference(commit_hash="fff666"),
            authors=("charlie",),
            timestamp=ts,
            raw_message="refactor(db): Refactor database layer",
        ),
    ]


@pytest.fixture()
def sample_notes(sample_items: list[ChangeItem], sample_range: ReleaseRange) -> ReleaseNotes:
    from releasepilot.processing.grouper import (
        extract_breaking_changes,
        extract_highlights,
        group_changes,
    )

    groups = group_changes(sample_items)
    highlights = extract_highlights(sample_items)
    breaking = extract_breaking_changes(sample_items)

    return ReleaseNotes(
        release_range=sample_range,
        groups=tuple(groups),
        highlights=tuple(highlights),
        breaking_changes=tuple(breaking),
        total_changes=len(sample_items),
    )


@pytest.fixture()
def default_render_config() -> RenderConfig:
    return RenderConfig()


@pytest.fixture()
def default_filter_config() -> FilterConfig:
    return FilterConfig()


def make_change_item(
    title: str,
    category: ChangeCategory = ChangeCategory.FEATURE,
    *,
    item_id: str = "",
    breaking: bool = False,
    importance: Importance = Importance.NORMAL,
    description: str = "",
    scope: str = "",
) -> ChangeItem:
    """Shared factory for constructing ChangeItems in tests."""
    item_id = item_id or f"id-{title[:12].replace(' ', '-')}"
    return ChangeItem(
        id=item_id,
        title=title,
        description=description,
        category=category,
        scope=scope,
        importance=importance,
        is_breaking=breaking,
        source=SourceReference(commit_hash="abc12345"),
        authors=("alice",),
        timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
    )
