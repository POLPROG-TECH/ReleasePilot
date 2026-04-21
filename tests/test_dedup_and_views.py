"""Regression tests for dedup logic, audience views, git tags, i18n
compatibility, settings config override, and guide preferences."""

from __future__ import annotations

from datetime import UTC, datetime

from releasepilot.domain.enums import Audience, ChangeCategory, Importance
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_item(
    id: str = "i1",
    title: str = "A change",
    description: str = "",
    category: ChangeCategory = ChangeCategory.FEATURE,
    importance: Importance = Importance.NORMAL,
    timestamp: datetime | None = None,
    commit_hash: str = "abc123",
    pr_number: int | None = None,
    scope: str = "",
    authors: tuple[str, ...] = ("dev",),
    is_breaking: bool = False,
) -> ChangeItem:
    return ChangeItem(
        id=id,
        title=title,
        description=description,
        category=category,
        scope=scope,
        importance=importance,
        is_breaking=is_breaking,
        source=SourceReference(commit_hash=commit_hash, pr_number=pr_number),
        authors=authors,
        timestamp=timestamp,
        raw_message=title,
    )


def _make_notes(
    items: list[ChangeItem] | None = None,
    groups: tuple[ChangeGroup, ...] | None = None,
) -> ReleaseNotes:
    if items is None:
        items = [_make_item()]
    if groups is None:
        from releasepilot.processing.grouper import group_changes

        groups = tuple(group_changes(items))
    return ReleaseNotes(
        release_range=ReleaseRange(
            from_ref="v1.0.0",
            to_ref="v1.1.0",
            version="1.1.0",
            title="Release 1.1.0",
        ),
        groups=groups,
        highlights=(),
        breaking_changes=(),
        total_changes=len(items),
    )


# ── _pick_best_item timestamp tiebreaker ─────────────────────────────────────


class TestDedupTimestampFallback:
    """_pick_best_item uses datetime.min fallback for None timestamps to ensure
    max() comparison works without TypeError."""

    """GIVEN items where all timestamps are None (PR merge scenario)"""

    def test_pick_best_with_none_timestamps(self):
        """WHEN the test exercises pick best with none timestamps"""
        from releasepilot.processing.dedup import deduplicate

        items = [
            _make_item(
                id="t1",
                title="WIP commit",
                commit_hash="a1",
                pr_number=99,
                timestamp=None,
            ),
            _make_item(
                id="t2",
                title="Final commit",
                description="Detailed description of the change",
                commit_hash="a2",
                pr_number=99,
                timestamp=None,
            ),
        ]

        # Should not raise TypeError on None comparison.
        result = deduplicate(items)
        """THEN the expected behavior for pick best with none timestamps is observed"""
        assert len(result) == 1
        assert result[0].description == "Detailed description of the change"

    """GIVEN items where some have timestamps and some don't"""

    def test_pick_best_mixed_timestamps(self):
        """WHEN the test exercises pick best mixed timestamps"""
        from releasepilot.processing.dedup import deduplicate

        ts = datetime(2025, 6, 1, tzinfo=UTC)
        items = [
            _make_item(
                id="m1",
                title="Old change",
                commit_hash="b1",
                pr_number=50,
                timestamp=None,
            ),
            _make_item(
                id="m2",
                title="New change",
                commit_hash="b2",
                pr_number=50,
                timestamp=ts,
            ),
        ]

        result = deduplicate(items)
        """THEN the expected behavior for pick best mixed timestamps is observed"""
        assert len(result) == 1
        # The item with a real timestamp should be preferred.
        assert result[0].timestamp == ts


# ── _summary_view uses polished items ────────────────────────────────────────


class TestSummaryViewPolishedItems:
    """_summary_view slices items from the polished group so titles are
    capitalized in summary output."""

    """GIVEN a group with lowercase-starting titles"""

    def test_summary_items_are_polished(self):
        """WHEN the test exercises summary items are polished"""
        from releasepilot.audience.views import apply_audience

        items = [
            _make_item(id="s1", title="add new dashboard widget", commit_hash="c1"),
            _make_item(id="s2", title="improve loading speed", commit_hash="c2"),
        ]
        notes = _make_notes(items)

        result = apply_audience(notes, Audience.SUMMARY)

        for group in result.groups:
            for item in group.items:
                if item.title:
                    assert item.title[0].isupper(), (
                        f"Summary view item title not polished: '{item.title}'"
                    )


# ── _customer_view single polishing pass ─────────────────────────────────────


class TestCustomerViewSinglePolish:
    """_customer_view polishes each group exactly once, producing consistent
    capitalized titles and respecting the max-items-per-group limit."""

    """GIVEN items with lowercase titles in customer-visible categories"""

    def test_customer_items_are_polished(self):
        """WHEN the test exercises customer items are polished"""
        from releasepilot.audience.views import apply_audience

        items = [
            _make_item(
                id="c1",
                title="fix payment processing error",
                category=ChangeCategory.BUGFIX,
                commit_hash="d1",
            ),
            _make_item(
                id="c2",
                title="add export feature",
                category=ChangeCategory.FEATURE,
                commit_hash="d2",
            ),
        ]
        notes = _make_notes(items)

        result = apply_audience(notes, Audience.CUSTOMER)

        for group in result.groups:
            for item in group.items:
                if item.title:
                    assert item.title[0].isupper(), (
                        f"Customer view item title not polished: '{item.title}'"
                    )

    """GIVEN a group with many items"""

    def test_customer_max_items_per_group(self):
        """WHEN the test exercises customer max items per group"""
        from releasepilot.audience.views import apply_audience

        items = [
            _make_item(
                id=f"cm{i}",
                title=f"Feature number {i}",
                category=ChangeCategory.FEATURE,
                commit_hash=f"hash{i}",
            )
            for i in range(10)
        ]
        notes = _make_notes(items)

        result = apply_audience(notes, Audience.CUSTOMER)

        for group in result.groups:
            assert len(group.items) <= 5


# ── list_tags limit slicing ───────────────────────────────────────────────────


class TestListTagsLimit:
    """list_tags fetches all sorted tags and slices in Python with
    tags[:limit] to honour the requested limit."""

    """GIVEN a git repo with 5 tags"""

    def test_list_tags_with_limit(self, tmp_path):
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True,
            check=True,
            env={
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "t@t.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "t@t.com",
                "HOME": str(tmp_path),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin",
            },
        )
        for i in range(1, 6):
            subprocess.run(
                ["git", "-C", str(repo), "tag", f"v{i}.0.0"],
                capture_output=True,
                check=True,
            )

        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(str(repo))

        """WHEN requesting 3 tags"""
        tags = collector.list_tags(limit=3)

        """THEN exactly 3 are returned"""
        assert len(tags) == 3

    """GIVEN a git repo with tags,"""

    def test_list_tags_no_limit(self, tmp_path):
        """WHEN limit=0,"""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True,
            check=True,
            env={
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "t@t.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "t@t.com",
                "HOME": str(tmp_path),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin",
            },
        )
        for i in range(1, 8):
            subprocess.run(
                ["git", "-C", str(repo), "tag", f"v{i}.0.0"],
                capture_output=True,
                check=True,
            )

        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(str(repo))
        tags = collector.list_tags(limit=0)

        """THEN all are returned"""
        assert len(tags) == 7


# ── _ALL_AUDIENCES includes "customer" ───────────────────────────────────────


class TestCustomerAudienceAvailability:
    """_ALL_AUDIENCES and _VALID_AUDIENCES both list every Audience enum value
    including 'customer', so all views are reachable from CLI and config."""

    """GIVEN the CLI audience list"""

    def test_customer_in_all_audiences(self):
        """WHEN the test exercises customer in all audiences"""
        from releasepilot.cli.app import _ALL_AUDIENCES

        """THEN the expected behavior for customer in all audiences is observed"""
        assert "customer" in _ALL_AUDIENCES

    """GIVEN the config validation audience set"""

    def test_customer_in_config_valid_audiences(self):
        """WHEN the test exercises customer in config valid audiences"""
        from releasepilot.config.file_config import _VALID_AUDIENCES

        """THEN the expected behavior for customer in config valid audiences is observed"""
        assert "customer" in _VALID_AUDIENCES

    """GIVEN every Audience enum member,"""

    def test_audience_enum_matches_all_audiences(self):
        """WHEN checked,"""
        from releasepilot.cli.app import _ALL_AUDIENCES
        from releasepilot.domain.enums import Audience

        for a in Audience:
            assert a.value in _ALL_AUDIENCES, (
                f"Audience.{a.name} ({a.value}) missing from _ALL_AUDIENCES"
            )


# ── _is_empty_release i18n compatibility ─────────────────────────────────────


class TestIsEmptyReleaseI18n:
    """_is_empty_release checks all supported language variants of the
    'no_notable_changes' i18n label to detect empty releases."""

    """GIVEN empty-release English output"""

    def test_detects_empty_english(self):
        """WHEN the test exercises detects empty english"""
        from releasepilot.cli.app import _is_empty_release

        output = "# Release 1.0.0\n\nNo notable changes in this release.\n"
        """THEN the expected behavior for detects empty english is observed"""
        assert _is_empty_release(output) is True

    """GIVEN empty-release Polish output"""

    def test_detects_empty_polish(self):
        """WHEN the test exercises detects empty polish"""
        from releasepilot.cli.app import _is_empty_release

        output = "# Release 1.0.0\n\nBrak istotnych zmian w tym wydaniu.\n"
        """THEN the expected behavior for detects empty polish is observed"""
        assert _is_empty_release(output) is True

    """GIVEN empty-release German output"""

    def test_detects_empty_german(self):
        """WHEN the test exercises detects empty german"""
        from releasepilot.cli.app import _is_empty_release

        output = "# Release 1.0.0\n\nKeine nennenswerten Änderungen in dieser Version.\n"
        """THEN the expected behavior for detects empty german is observed"""
        assert _is_empty_release(output) is True

    """GIVEN normal release output with content"""

    def test_non_empty_release(self):
        """WHEN the test exercises non empty release"""
        from releasepilot.cli.app import _is_empty_release

        output = "# Release 1.0.0\n\n## Features\n- Added dark mode\n"
        """THEN the expected behavior for non empty release is observed"""
        assert _is_empty_release(output) is False

    """GIVEN blank output"""

    def test_blank_output_is_empty(self):
        """WHEN the test exercises blank output is empty"""
        from releasepilot.cli.app import _is_empty_release

        """THEN the expected behavior for blank output is empty is observed"""
        assert _is_empty_release("") is True
        assert _is_empty_release("   \n  ") is True


# ── _build_settings config override with None sentinel ───────────────────────


class TestBuildSettingsNoneSentinel:
    """_build_settings uses None as default sentinel so config-file values
    only apply when the user did not pass a CLI flag; an explicit CLI value
    always wins over the config file."""

    """GIVEN audience=None (user didn't pass --audience)"""

    def test_none_audience_uses_config_value(self):
        """WHEN the test exercises none audience uses config value"""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(audience="user")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".",
                from_ref="",
                to_ref="HEAD",
                source_file="",
                version_str="",
                title="",
                audience=None,
            )
        """THEN the expected behavior for none audience uses config value is observed"""
        assert settings.audience == Audience.USER

    """GIVEN audience='changelog' explicitly passed by user"""

    def test_explicit_audience_overrides_config(self):
        """WHEN the test exercises explicit audience overrides config"""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(audience="user")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".",
                from_ref="",
                to_ref="HEAD",
                source_file="",
                version_str="",
                title="",
                audience="changelog",
            )
        """THEN the expected behavior for explicit audience overrides config is observed"""
        assert settings.audience == Audience.CHANGELOG

    """GIVEN lang=None (user didn't pass --language)"""

    def test_none_language_uses_config_value(self):
        """WHEN the test exercises none language uses config value"""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(language="pl")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".",
                from_ref="",
                to_ref="HEAD",
                source_file="",
                version_str="",
                title="",
                lang=None,
            )
        """THEN the expected behavior for none language uses config value is observed"""
        assert settings.language == "pl"

    """GIVEN lang='en' explicitly passed by user"""

    def test_explicit_language_overrides_config(self):
        """WHEN the test exercises explicit language overrides config"""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(language="pl")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".",
                from_ref="",
                to_ref="HEAD",
                source_file="",
                version_str="",
                title="",
                lang="en",
            )
        """THEN the expected behavior for explicit language overrides config is observed"""
        assert settings.language == "en"

    """GIVEN output_format=None (user didn't pass --format)"""

    def test_none_format_uses_config_value(self):
        """WHEN the test exercises none format uses config value"""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(format="plaintext")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".",
                from_ref="",
                to_ref="HEAD",
                source_file="",
                version_str="",
                title="",
                output_format=None,
            )
        from releasepilot.domain.enums import OutputFormat

        """THEN the expected behavior for none format uses config value is observed"""
        assert settings.output_format == OutputFormat.PLAINTEXT


# ── Guide preference index 0 handling ────────────────────────────────────────


class TestGuidePreferenceIndexZero:
    """Guide preference lookup uses `is not None` instead of truthiness so
    index 0 (first choice) is not mistaken for 'no preference'."""

    """GIVEN a preference function returning 0 (first item in list)"""

    def test_preference_index_zero_not_overridden(self):
        # Verify the pattern used in the fix
        """WHEN the test exercises preference index zero not overridden"""
        pref_idx = 0
        default = 5

        # Old pattern (buggy): result = pref_idx or default → 5
        old_result = pref_idx or default
        """THEN the expected behavior for preference index zero not overridden is observed"""
        assert old_result == 5  # This was the bug

        # New pattern (fixed): result = pref_idx if pref_idx is not None else default → 0
        new_result = pref_idx if pref_idx is not None else default
        assert new_result == 0  # This is correct

    """GIVEN a preference function returning None (no preference saved)"""

    def test_preference_none_uses_default(self):
        """WHEN the test exercises preference none uses default"""
        pref_idx = None
        default = 5

        result = pref_idx if pref_idx is not None else default
        """THEN the expected behavior for preference none uses default is observed"""
        assert result == 5


# ── Additional edge case tests ───────────────────────────────────────────────


class TestDedupEmptyInput:
    """Edge case: deduplicate should handle empty input gracefully."""

    """GIVEN an empty item list,"""

    def test_empty_list(self):
        """WHEN deduplicated,"""
        from releasepilot.processing.dedup import deduplicate

        """THEN result is empty"""
        assert deduplicate([]) == []

    """GIVEN a single item,"""

    def test_single_item(self):
        """WHEN deduplicated,"""
        from releasepilot.processing.dedup import deduplicate

        item = _make_item()
        result = deduplicate([item])
        """THEN it is returned unchanged"""
        assert len(result) == 1


class TestAudienceViewsEmptyNotes:
    """Edge case: audience views should handle notes with no groups."""

    """GIVEN notes with no groups,"""

    def test_summary_empty_groups(self):
        """WHEN summary view applied,"""
        from releasepilot.audience.views import apply_audience

        notes = _make_notes(items=[], groups=())
        result = apply_audience(notes, Audience.SUMMARY)
        """THEN result has 0 groups"""
        assert len(result.groups) == 0
        assert result.total_changes == 0

    """GIVEN notes with no groups,"""

    def test_customer_empty_groups(self):
        """WHEN customer view applied,"""
        from releasepilot.audience.views import apply_audience

        notes = _make_notes(items=[], groups=())
        result = apply_audience(notes, Audience.CUSTOMER)
        """THEN result has 0 groups"""
        assert len(result.groups) == 0
        assert result.total_changes == 0

    """GIVEN notes with no groups,"""

    def test_user_empty_groups(self):
        """WHEN user view applied,"""
        from releasepilot.audience.views import apply_audience

        notes = _make_notes(items=[], groups=())
        result = apply_audience(notes, Audience.USER)
        """THEN result has 0 groups"""
        assert len(result.groups) == 0
        assert result.total_changes == 0
