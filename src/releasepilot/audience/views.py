"""Audience-specific view transformations.

Transforms ReleaseNotes for different audiences by:
- Filtering categories (e.g., hide refactors from users)
- Adjusting tone/detail level
- Selecting relevant highlights

Each audience function takes ReleaseNotes and returns new ReleaseNotes
with audience-appropriate content.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from releasepilot.domain.enums import Audience, ChangeCategory
from releasepilot.domain.models import ChangeGroup, ChangeItem, ReleaseNotes

_AudienceTransform = Callable[[ReleaseNotes], ReleaseNotes]


def apply_audience(notes: ReleaseNotes, audience: Audience) -> ReleaseNotes:
    """Apply audience-specific transformations to release notes."""
    transforms: dict[Audience, _AudienceTransform] = {
        Audience.TECHNICAL: _technical_view,
        Audience.USER: _user_view,
        Audience.SUMMARY: _summary_view,
        Audience.CHANGELOG: _changelog_view,
        Audience.CUSTOMER: _customer_view,
        Audience.EXECUTIVE: _executive_view,
        Audience.NARRATIVE: _narrative_view,
        Audience.CUSTOMER_NARRATIVE: _customer_narrative_view,
    }
    transform = transforms.get(audience, _changelog_view)
    return transform(notes)


def _technical_view(notes: ReleaseNotes) -> ReleaseNotes:
    """Full technical detail — all categories, all items."""
    return notes


def _user_view(notes: ReleaseNotes) -> ReleaseNotes:
    """User-facing view — hide internal categories, polish titles."""
    hidden = {
        ChangeCategory.REFACTOR,
        ChangeCategory.INFRASTRUCTURE,
        ChangeCategory.OTHER,
    }
    filtered_groups = tuple(
        _polish_group_for_users(g) for g in notes.groups if g.category not in hidden
    )
    filtered_highlights = tuple(
        _polish_item_for_users(i) for i in notes.highlights if i.category not in hidden
    )
    total = sum(len(g.items) for g in filtered_groups)

    return replace(
        notes,
        groups=filtered_groups,
        highlights=filtered_highlights,
        total_changes=total,
    )


def _summary_view(notes: ReleaseNotes) -> ReleaseNotes:
    """Concise summary — only top items per category, polished titles.

    Hides internal categories and limits each group to 3 items.
    Designed for quick scanning: a short, focused overview.
    """
    max_per_group = 3
    hidden = {
        ChangeCategory.REFACTOR,
        ChangeCategory.INFRASTRUCTURE,
        ChangeCategory.DOCUMENTATION,
        ChangeCategory.OTHER,
    }
    summarized_groups = tuple(
        replace(polished, items=polished.items[:max_per_group])
        for g in notes.groups
        if g.category not in hidden
        for polished in (_polish_group_for_users(g),)
    )
    total = sum(len(g.items) for g in summarized_groups)

    return replace(
        notes,
        groups=summarized_groups,
        total_changes=total,
    )


def _changelog_view(notes: ReleaseNotes) -> ReleaseNotes:
    """Standard changelog — all categories, polished titles.

    Includes everything but polishes titles for readability.
    Unlike _technical_view (which keeps raw titles and all metadata),
    changelog mode produces cleaner output suitable for CHANGELOG.md files.
    """
    polished_groups = tuple(_polish_group_for_users(g) for g in notes.groups)
    polished_highlights = tuple(_polish_item_for_users(i) for i in notes.highlights)
    return replace(
        notes,
        groups=polished_groups,
        highlights=polished_highlights,
    )


def _executive_view(notes: ReleaseNotes) -> ReleaseNotes:
    """Executive view — hide internal-only categories, polish titles.

    This provides a clean ReleaseNotes that the executive brief composer
    can then transform into business-oriented output.
    """
    hidden = {
        ChangeCategory.REFACTOR,
        ChangeCategory.INFRASTRUCTURE,
        ChangeCategory.DOCUMENTATION,
        ChangeCategory.OTHER,
    }
    filtered_groups = tuple(
        _polish_group_for_users(g) for g in notes.groups if g.category not in hidden
    )
    filtered_highlights = tuple(
        _polish_item_for_users(i) for i in notes.highlights if i.category not in hidden
    )
    total = sum(len(g.items) for g in filtered_groups)

    return replace(
        notes,
        groups=filtered_groups,
        highlights=filtered_highlights,
        total_changes=total,
    )


def _customer_view(notes: ReleaseNotes) -> ReleaseNotes:
    """Customer-facing view — high-level, polished, outcome-focused.

    Hides all internal/technical categories and limits output to changes
    that directly affect customers.  Titles are polished for readability.
    """
    hidden = {
        ChangeCategory.REFACTOR,
        ChangeCategory.INFRASTRUCTURE,
        ChangeCategory.DOCUMENTATION,
        ChangeCategory.DEPRECATION,
        ChangeCategory.OTHER,
    }
    max_per_group = 5
    filtered_groups = tuple(
        replace(
            polished,
            items=polished.items[:max_per_group],
        )
        for g in notes.groups
        if g.category not in hidden and g.items
        for polished in (_polish_group_for_users(g),)
    )
    filtered_highlights = tuple(
        _polish_item_for_users(i) for i in notes.highlights if i.category not in hidden
    )[:5]
    total = sum(len(g.items) for g in filtered_groups)

    return replace(
        notes,
        groups=filtered_groups,
        highlights=filtered_highlights,
        total_changes=total,
    )


def _polish_group_for_users(group: ChangeGroup) -> ChangeGroup:
    """Polish a change group for user-facing display."""
    polished_items = tuple(_polish_item_for_users(item) for item in group.items)
    return replace(group, items=polished_items)


def _polish_item_for_users(item: ChangeItem) -> ChangeItem:
    """Polish a change item for user-facing display.

    Removes technical prefixes and ensures the title reads naturally.
    """
    title = item.title
    # Remove scope prefix if present (e.g., "auth: " becomes "")
    # but keep scope metadata for grouping
    if title and title[0].islower():
        title = title[0].upper() + title[1:]
    return replace(item, title=title)


def _narrative_view(notes: ReleaseNotes) -> ReleaseNotes:
    """Narrative view — all categories, polished titles.

    Prepares ReleaseNotes for the narrative pipeline which transforms
    them into continuous prose.  Keeps all categories (including
    infrastructure, refactoring) since the narrative composer controls
    what appears in the final text.
    """
    polished_groups = tuple(_polish_group_for_users(g) for g in notes.groups)
    polished_highlights = tuple(_polish_item_for_users(i) for i in notes.highlights)
    return replace(
        notes,
        groups=polished_groups,
        highlights=polished_highlights,
    )


def _customer_narrative_view(notes: ReleaseNotes) -> ReleaseNotes:
    """Customer narrative view — hide internal categories, polish titles.

    Prepares ReleaseNotes for the customer-facing narrative pipeline.
    Hides internal technical categories before the narrative composer
    converts the remaining changes into customer-friendly prose.
    """
    hidden = {
        ChangeCategory.REFACTOR,
        ChangeCategory.INFRASTRUCTURE,
        ChangeCategory.DOCUMENTATION,
        ChangeCategory.OTHER,
    }
    filtered_groups = tuple(
        _polish_group_for_users(g) for g in notes.groups if g.category not in hidden
    )
    filtered_highlights = tuple(
        _polish_item_for_users(i) for i in notes.highlights if i.category not in hidden
    )
    total = sum(len(g.items) for g in filtered_groups)

    return replace(
        notes,
        groups=filtered_groups,
        highlights=filtered_highlights,
        total_changes=total,
    )
