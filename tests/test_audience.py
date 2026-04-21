"""Tests for audience-specific views."""

from __future__ import annotations

from releasepilot.audience.views import apply_audience
from releasepilot.domain.enums import Audience, ChangeCategory
from releasepilot.domain.models import ReleaseNotes


class TestTechnicalView:
    """Scenarios for technical audience view."""

    """GIVEN full release notes"""

    def test_all_categories_included(self, sample_notes: ReleaseNotes):
        """WHEN applying technical audience"""
        result = apply_audience(sample_notes, Audience.TECHNICAL)

        """THEN all groups are preserved (including infra and refactor)"""
        categories = {g.category for g in result.groups}
        assert ChangeCategory.INFRASTRUCTURE in categories
        assert ChangeCategory.REFACTOR in categories


class TestUserView:
    """Scenarios for user audience view."""

    """GIVEN release notes with infra and refactor groups"""

    def test_internal_categories_hidden(self, sample_notes: ReleaseNotes):
        """WHEN applying user audience"""
        result = apply_audience(sample_notes, Audience.USER)

        """THEN internal categories are hidden"""
        categories = {g.category for g in result.groups}
        assert ChangeCategory.REFACTOR not in categories
        assert ChangeCategory.INFRASTRUCTURE not in categories

    """GIVEN release notes with feature and bugfix groups"""

    def test_user_facing_categories_preserved(self, sample_notes: ReleaseNotes):
        """WHEN applying user audience"""
        result = apply_audience(sample_notes, Audience.USER)

        """THEN user-facing categories remain"""
        categories = {g.category for g in result.groups}
        assert ChangeCategory.FEATURE in categories
        assert ChangeCategory.BUGFIX in categories

    """GIVEN release notes with mixed categories"""

    def test_total_changes_updated(self, sample_notes: ReleaseNotes):
        """WHEN applying user audience"""
        result = apply_audience(sample_notes, Audience.USER)

        """THEN total_changes reflects the filtered count"""
        assert result.total_changes < sample_notes.total_changes


class TestSummaryView:
    """Scenarios for summary audience view."""

    """GIVEN release notes"""

    def test_max_items_per_group(self, sample_notes: ReleaseNotes):
        """WHEN applying summary audience"""
        result = apply_audience(sample_notes, Audience.SUMMARY)

        """THEN each group has at most 3 items"""
        for group in result.groups:
            assert len(group.items) <= 3

    """GIVEN release notes"""

    def test_internal_categories_hidden(self, sample_notes: ReleaseNotes):
        """WHEN applying summary audience"""
        result = apply_audience(sample_notes, Audience.SUMMARY)

        """THEN internal categories are excluded"""
        categories = {g.category for g in result.groups}
        assert ChangeCategory.REFACTOR not in categories


class TestChangelogView:
    """Scenarios for changelog audience view."""

    """GIVEN release notes"""

    def test_all_categories_included(self, sample_notes: ReleaseNotes):
        """WHEN applying changelog audience"""
        result = apply_audience(sample_notes, Audience.CHANGELOG)

        """THEN all groups are preserved"""
        assert len(result.groups) == len(sample_notes.groups)

    """GIVEN release notes with lowercase-starting titles"""

    def test_titles_polished(self, sample_notes: ReleaseNotes):
        """WHEN applying changelog audience"""
        result = apply_audience(sample_notes, Audience.CHANGELOG)

        """THEN titles are capitalized (polished)"""
        for group in result.groups:
            for item in group.items:
                if item.title:
                    assert item.title[0].isupper() or not item.title[0].isalpha()


class TestChangelogVsTechnicalDifference:
    """Scenarios for changelog vs technical view differences."""

    """GIVEN release notes"""

    def test_technical_keeps_raw_titles(self, sample_notes: ReleaseNotes):
        """WHEN the test exercises technical keeps raw titles"""
        tech = apply_audience(sample_notes, Audience.TECHNICAL)

        """THEN technical view returns the exact original notes object"""
        assert tech is sample_notes

    """GIVEN release notes"""

    def test_changelog_polishes_titles(self, sample_notes: ReleaseNotes):
        """WHEN the test exercises changelog polishes titles"""
        changelog = apply_audience(sample_notes, Audience.CHANGELOG)

        """THEN changelog view returns a NEW object (not identity)"""
        assert changelog is not sample_notes
