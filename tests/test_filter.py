"""Tests for the noise filter."""

from __future__ import annotations

from releasepilot.config.settings import FilterConfig
from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import ChangeItem
from releasepilot.processing.filter import filter_changes, mark_noise


class TestNoisePatternFiltering:
    """Scenarios for noise pattern filtering."""

    """GIVEN a merge commit"""

    def test_merge_commits_filtered(self):
        items = [
            ChangeItem(id="m1", title="Merge branch 'main'", raw_message="Merge branch 'main'"),
        ]
        config = FilterConfig()

        """WHEN filtering"""
        result = filter_changes(items, config)

        """THEN the merge commit is removed"""
        assert len(result) == 0

    """GIVEN a WIP commit"""

    def test_wip_commits_filtered(self):
        items = [
            ChangeItem(id="w1", title="wip: trying something", raw_message="wip: trying something"),
        ]
        config = FilterConfig()

        """WHEN filtering"""
        result = filter_changes(items, config)

        """THEN the WIP commit is removed"""
        assert len(result) == 0

    """GIVEN a fixup commit"""

    def test_fixup_commits_filtered(self):
        items = [
            ChangeItem(
                id="f1", title="fixup! previous commit", raw_message="fixup! previous commit"
            ),
        ]
        config = FilterConfig()

        """WHEN filtering"""
        result = filter_changes(items, config)

        """THEN the fixup commit is removed"""
        assert len(result) == 0

    """GIVEN a meaningful commit"""

    def test_meaningful_commits_preserved(self):
        items = [
            ChangeItem(
                id="g1",
                title="Add user profile page",
                raw_message="Add user profile page",
            ),
        ]
        config = FilterConfig()

        """WHEN filtering"""
        result = filter_changes(items, config)

        """THEN the commit is preserved"""
        assert len(result) == 1
        assert result[0].id == "g1"


class TestShortTitleFiltering:
    """Scenarios for short title filtering."""

    """GIVEN a commit with a 2-character title"""

    def test_very_short_titles_filtered(self):
        items = [ChangeItem(id="s1", title="ok", raw_message="ok")]
        config = FilterConfig()

        """WHEN filtering"""
        result = filter_changes(items, config)

        """THEN it is filtered out"""
        assert len(result) == 0

    """GIVEN a commit with a sufficient title"""

    def test_adequate_titles_preserved(self):
        items = [ChangeItem(id="s2", title="Fix login bug", raw_message="Fix login bug")]
        config = FilterConfig()

        """WHEN filtering"""
        result = filter_changes(items, config)

        """THEN it is preserved"""
        assert len(result) == 1


class TestCategoryFiltering:
    """Scenarios for category-based filtering."""

    """GIVEN items and a config excluding REFACTOR"""

    def test_exclude_specific_category(self):
        items = [
            ChangeItem(
                id="c1", title="Add feature", category=ChangeCategory.FEATURE, raw_message="x"
            ),
            ChangeItem(
                id="c2", title="Refactor code", category=ChangeCategory.REFACTOR, raw_message="y"
            ),
        ]
        config = FilterConfig(exclude_categories=frozenset({ChangeCategory.REFACTOR}))

        """WHEN filtering"""
        result = filter_changes(items, config)

        """THEN refactor is excluded"""
        assert len(result) == 1
        assert result[0].id == "c1"

    """GIVEN items and a config including only FEATURE and BUGFIX"""

    def test_include_only_specific_categories(self):
        items = [
            ChangeItem(
                id="i1", title="Add thing", category=ChangeCategory.FEATURE, raw_message="x"
            ),
            ChangeItem(id="i2", title="Fix thing", category=ChangeCategory.BUGFIX, raw_message="y"),
            ChangeItem(
                id="i3", title="Docs update", category=ChangeCategory.DOCUMENTATION, raw_message="z"
            ),
        ]
        config = FilterConfig(
            include_categories=frozenset({ChangeCategory.FEATURE, ChangeCategory.BUGFIX})
        )

        """WHEN filtering"""
        result = filter_changes(items, config)

        """THEN only feature and bugfix are kept"""
        assert len(result) == 2
        assert {r.id for r in result} == {"i1", "i2"}


class TestMarkNoise:
    """Scenarios for marking noisy items without removal."""

    """GIVEN a mix of meaningful and noisy items"""

    def test_noisy_items_marked_not_removed(self):
        items = [
            ChangeItem(id="n1", title="Merge branch 'dev'", raw_message="Merge branch 'dev'"),
            ChangeItem(id="n2", title="Add search feature", raw_message="Add search feature"),
        ]
        config = FilterConfig()

        """WHEN marking noise"""
        result = mark_noise(items, config)

        """THEN both items remain but noise is marked"""
        assert len(result) == 2
        assert result[0].importance == Importance.NOISE
        assert result[1].importance == Importance.NORMAL
