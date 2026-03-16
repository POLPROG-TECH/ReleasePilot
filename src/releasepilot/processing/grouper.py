"""Change grouper.

Groups classified and filtered ChangeItems into ChangeGroups,
sorted deterministically by category display order then by item sort key.
"""

from __future__ import annotations

from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import ChangeGroup, ChangeItem


def group_changes(items: list[ChangeItem]) -> list[ChangeGroup]:
    """Group items by category and sort deterministically.

    Returns ChangeGroups ordered by category priority (breaking first, other last).
    Items within each group are sorted by scope then title.
    Empty groups are excluded.
    """
    buckets: dict[ChangeCategory, list[ChangeItem]] = {}

    for item in items:
        buckets.setdefault(item.category, []).append(item)

    groups: list[ChangeGroup] = []
    for category in sorted(buckets.keys(), key=lambda c: c.sort_order):
        sorted_items = sorted(buckets[category], key=lambda i: i.sort_key)
        groups.append(
            ChangeGroup(
                category=category,
                items=tuple(sorted_items),
            )
        )

    return groups


def extract_highlights(items: list[ChangeItem]) -> list[ChangeItem]:
    """Extract notable items that deserve special mention.

    Highlights are: breaking changes, security fixes, and high-importance items.
    """
    return sorted(
        [
            item
            for item in items
            if item.is_breaking
            or item.category == ChangeCategory.SECURITY
            or item.importance.value == "high"
        ],
        key=lambda i: i.sort_key,
    )


def extract_breaking_changes(items: list[ChangeItem]) -> list[ChangeItem]:
    """Extract all breaking changes for dedicated rendering."""
    return sorted(
        [item for item in items if item.is_breaking],
        key=lambda i: i.sort_key,
    )
