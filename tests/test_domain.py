"""Tests for domain models and enums."""

from __future__ import annotations

from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import (
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)


class TestSourceReference:
    """Scenarios for SourceReference model."""

    """GIVEN a source reference with a full commit hash"""

    def test_short_hash(self):
        ref = SourceReference(commit_hash="abc123def4567890")

        """WHEN accessing the short hash"""
        result = ref.short_hash

        """THEN it returns the first 8 characters"""
        assert result == "abc123de"

    """GIVEN a source reference with no commit hash"""

    def test_short_hash_empty(self):
        ref = SourceReference()

        """WHEN accessing the short hash"""
        result = ref.short_hash

        """THEN it returns an empty string"""
        assert result == ""


class TestChangeItem:
    """Scenarios for ChangeItem model."""

    """GIVEN two items with different categories and scopes"""

    def test_sort_key_deterministic(self):
        item_a = ChangeItem(id="a", title="Fix bug", category=ChangeCategory.BUGFIX, scope="api")
        item_b = ChangeItem(
            id="b", title="Add feature", category=ChangeCategory.FEATURE, scope="ui"
        )

        """WHEN comparing their sort keys"""
        key_a = item_a.sort_key
        key_b = item_b.sort_key

        """THEN features sort before bugfixes (lower sort_order)"""
        assert key_b < key_a

    """GIVEN two items in the same category with different scopes"""

    def test_sort_key_by_scope(self):
        item_a = ChangeItem(id="a", title="Z item", category=ChangeCategory.FEATURE, scope="auth")
        item_b = ChangeItem(id="b", title="A item", category=ChangeCategory.FEATURE, scope="ui")

        """WHEN comparing sort keys"""

        """THEN items are sorted by scope alphabetically"""
        assert item_a.sort_key < item_b.sort_key

    """GIVEN a frozen change item"""

    def test_frozen_immutability(self):
        item = ChangeItem(id="test", title="Test")

        """WHEN attempting to modify a field"""

        """THEN it raises a FrozenInstanceError"""
        import dataclasses

        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            item.title = "Modified"  # type: ignore[misc]


class TestReleaseRange:
    """Scenarios for ReleaseRange model."""

    """GIVEN a range with an explicit title"""

    def test_display_title_with_title(self):
        rr = ReleaseRange(from_ref="v1.0", to_ref="v1.1", title="Big Release")

        """WHEN accessing display_title"""

        """THEN the explicit title is used"""
        assert rr.display_title == "Big Release"

    """GIVEN a range with a version but no title"""

    def test_display_title_with_version(self):
        rr = ReleaseRange(from_ref="v1.0", to_ref="v1.1", version="1.1.0")

        """WHEN accessing display_title"""

        """THEN the version is formatted"""
        assert rr.display_title == "Release 1.1.0"

    """GIVEN a range with no title or version"""

    def test_display_title_fallback(self):
        rr = ReleaseRange(from_ref="v1.0", to_ref="v1.1")

        """WHEN accessing display_title"""

        """THEN the ref range is used"""
        assert rr.display_title == "v1.0..v1.1"


class TestReleaseNotes:
    """Scenarios for ReleaseNotes model."""

    """GIVEN release notes with zero total changes"""

    def test_is_empty_when_no_changes(self):
        notes = ReleaseNotes(
            release_range=ReleaseRange(from_ref="a", to_ref="b"),
            groups=(),
            total_changes=0,
        )

        """WHEN checking if empty"""

        """THEN it reports as empty"""
        assert notes.is_empty is True

    """GIVEN release notes with some changes"""

    def test_is_not_empty_with_changes(self):
        notes = ReleaseNotes(
            release_range=ReleaseRange(from_ref="a", to_ref="b"),
            groups=(),
            total_changes=5,
        )

        """WHEN checking if empty"""

        """THEN it reports as non-empty"""
        assert notes.is_empty is False


class TestChangeCategory:
    """Scenarios for ChangeCategory enum."""

    """GIVEN each category"""

    def test_display_label(self):
        """WHEN accessing its display label"""

        """THEN every category has a non-empty label"""
        for cat in ChangeCategory:
            assert cat.display_label, f"{cat} missing display label"

    """GIVEN all categories"""

    def test_sort_order_unique(self):
        orders = [c.sort_order for c in ChangeCategory]

        """WHEN checking sort orders"""

        """THEN all are unique"""
        assert len(orders) == len(set(orders))

    """GIVEN breaking and other categories"""

    def test_breaking_sorts_first(self):
        """WHEN comparing sort orders"""

        """THEN breaking has the lowest sort order"""
        assert ChangeCategory.BREAKING.sort_order < ChangeCategory.FEATURE.sort_order
        assert ChangeCategory.BREAKING.sort_order < ChangeCategory.OTHER.sort_order
