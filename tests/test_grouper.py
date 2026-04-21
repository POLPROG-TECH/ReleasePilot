"""Tests for change grouping."""

from __future__ import annotations

from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import ChangeItem
from releasepilot.processing.grouper import (
    extract_breaking_changes,
    extract_highlights,
    group_changes,
)


class TestGroupChanges:
    """Scenarios for grouping changes by category."""

    """GIVEN a list of items with different categories"""

    def test_groups_by_category(self, sample_items):
        """WHEN grouping changes"""
        groups = group_changes(sample_items)

        """THEN each unique category gets a group"""
        categories = {g.category for g in groups}
        assert ChangeCategory.FEATURE in categories
        assert ChangeCategory.BUGFIX in categories
        assert ChangeCategory.BREAKING in categories

    """GIVEN items including breaking and feature changes"""

    def test_groups_sorted_by_priority(self, sample_items):
        """WHEN grouping changes"""
        groups = group_changes(sample_items)

        """THEN groups are sorted by category priority"""
        sort_orders = [g.sort_key for g in groups]
        assert sort_orders == sorted(sort_orders)

    """GIVEN multiple items in the same category with different scopes"""

    def test_items_within_group_sorted(self):
        items = [
            ChangeItem(id="1", title="Zebra feature", category=ChangeCategory.FEATURE, scope="z"),
            ChangeItem(id="2", title="Alpha feature", category=ChangeCategory.FEATURE, scope="a"),
        ]

        """WHEN grouping changes"""
        groups = group_changes(items)

        """THEN items within the group are sorted by scope"""
        assert groups[0].items[0].scope == "a"
        assert groups[0].items[1].scope == "z"

    """GIVEN no items"""

    def test_empty_input(self):
        """WHEN grouping changes"""
        groups = group_changes([])

        """THEN no groups are produced"""
        assert groups == []


class TestExtractHighlights:
    """Scenarios for extracting highlighted changes."""

    """GIVEN items including breaking changes"""

    def test_breaking_changes_highlighted(self, sample_items):
        """WHEN extracting highlights"""
        highlights = extract_highlights(sample_items)

        """THEN breaking changes are included"""
        breaking_ids = {h.id for h in highlights if h.is_breaking}
        assert len(breaking_ids) > 0

    """GIVEN items with high importance"""

    def test_high_importance_highlighted(self, sample_items):
        """WHEN extracting highlights"""
        highlights = extract_highlights(sample_items)

        """THEN high-importance items are included"""
        high_ids = {h.id for h in highlights if h.importance == Importance.HIGH}
        assert len(high_ids) > 0


class TestExtractBreakingChanges:
    """Scenarios for extracting breaking changes."""

    """GIVEN a mix of breaking and non-breaking items"""

    def test_only_breaking_extracted(self, sample_items):
        """WHEN extracting breaking changes"""
        breaking = extract_breaking_changes(sample_items)

        """THEN only breaking items are returned"""
        assert all(item.is_breaking for item in breaking)

    """GIVEN items with no breaking changes"""

    def test_no_breaking_returns_empty(self):
        items = [
            ChangeItem(id="1", title="Simple fix", category=ChangeCategory.BUGFIX),
        ]

        """WHEN extracting breaking changes"""
        breaking = extract_breaking_changes(items)

        """THEN the result is empty"""
        assert breaking == []
