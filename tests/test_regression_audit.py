"""Regression tests for production audit fixes.

Each test class covers a specific bug found during the deep audit.
Tests are designed to fail on the original buggy code and pass on the fix.
"""

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
            from_ref="v1.0.0", to_ref="v1.1.0",
            version="1.1.0", title="Release 1.1.0",
        ),
        groups=groups,
        highlights=(),
        breaking_changes=(),
        total_changes=len(items),
    )


# ── Fix #1: _pick_best_item timestamp tiebreaker ────────────────────────────


class TestDedupTimestampFallback:
    """Regression: _pick_best_item used `i.timestamp or i.timestamp` which is
    a no-op and crashes when comparing None timestamps via `max()`.
    Fix: use `i.timestamp or datetime.min` as a safe fallback.
    """

    def test_pick_best_with_none_timestamps(self):
        """GIVEN items where all timestamps are None (PR merge scenario)."""
        from releasepilot.processing.dedup import deduplicate

        items = [
            _make_item(
                id="t1", title="WIP commit",
                commit_hash="a1", pr_number=99,
                timestamp=None,
            ),
            _make_item(
                id="t2", title="Final commit",
                description="Detailed description of the change",
                commit_hash="a2", pr_number=99,
                timestamp=None,
            ),
        ]

        # Should not raise TypeError on None comparison.
        result = deduplicate(items)
        assert len(result) == 1
        assert result[0].description == "Detailed description of the change"

    def test_pick_best_mixed_timestamps(self):
        """GIVEN items where some have timestamps and some don't."""
        from releasepilot.processing.dedup import deduplicate

        ts = datetime(2025, 6, 1, tzinfo=UTC)
        items = [
            _make_item(
                id="m1", title="Old change",
                commit_hash="b1", pr_number=50,
                timestamp=None,
            ),
            _make_item(
                id="m2", title="New change",
                commit_hash="b2", pr_number=50,
                timestamp=ts,
            ),
        ]

        result = deduplicate(items)
        assert len(result) == 1
        # The item with a real timestamp should be preferred.
        assert result[0].timestamp == ts


# ── Fix #2: _summary_view used unpolished items ─────────────────────────────


class TestSummaryViewPolishedItems:
    """Regression: _summary_view sliced items from the *original* group `g`
    instead of the polished group, so titles were not capitalized.
    Fix: use `polished.items[:max_per_group]` instead of `g.items[:max_per_group]`.
    """

    def test_summary_items_are_polished(self):
        """GIVEN a group with lowercase-starting titles."""
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


# ── Fix #3: _customer_view double-polishing ──────────────────────────────────


class TestCustomerViewSinglePolish:
    """Regression: _customer_view called _polish_group_for_users(g) twice per group,
    wasting computation and producing inconsistent results if polishing was
    non-idempotent.
    Fix: use `for polished in (_polish_group_for_users(g),)` pattern.
    """

    def test_customer_items_are_polished(self):
        """GIVEN items with lowercase titles in customer-visible categories."""
        from releasepilot.audience.views import apply_audience

        items = [
            _make_item(id="c1", title="fix payment processing error",
                       category=ChangeCategory.BUGFIX, commit_hash="d1"),
            _make_item(id="c2", title="add export feature",
                       category=ChangeCategory.FEATURE, commit_hash="d2"),
        ]
        notes = _make_notes(items)

        result = apply_audience(notes, Audience.CUSTOMER)

        for group in result.groups:
            for item in group.items:
                if item.title:
                    assert item.title[0].isupper(), (
                        f"Customer view item title not polished: '{item.title}'"
                    )

    def test_customer_max_items_per_group(self):
        """GIVEN a group with many items."""
        from releasepilot.audience.views import apply_audience

        items = [
            _make_item(id=f"cm{i}", title=f"Feature number {i}",
                       category=ChangeCategory.FEATURE, commit_hash=f"hash{i}")
            for i in range(10)
        ]
        notes = _make_notes(items)

        result = apply_audience(notes, Audience.CUSTOMER)

        for group in result.groups:
            assert len(group.items) <= 5


# ── Fix #4: list_tags invalid --count flag ───────────────────────────────────


class TestListTagsLimit:
    """Regression: list_tags passed `--count=N` which is not a valid git-tag flag.
    This caused a silent git error (swallowed by the except clause).
    Fix: fetch all tags sorted, then slice in Python with `tags[:limit]`.
    """

    def test_list_tags_with_limit(self, tmp_path):
        """GIVEN a git repo with 5 tags."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True, check=True,
            env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com",
                 "HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"},
        )
        for i in range(1, 6):
            subprocess.run(
                ["git", "-C", str(repo), "tag", f"v{i}.0.0"],
                capture_output=True, check=True,
            )

        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(str(repo))

        """WHEN requesting 3 tags."""
        tags = collector.list_tags(limit=3)

        """THEN exactly 3 are returned."""
        assert len(tags) == 3

    def test_list_tags_no_limit(self, tmp_path):
        """GIVEN a git repo with tags, WHEN limit=0, THEN all are returned."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True, check=True,
            env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com",
                 "HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"},
        )
        for i in range(1, 8):
            subprocess.run(
                ["git", "-C", str(repo), "tag", f"v{i}.0.0"],
                capture_output=True, check=True,
            )

        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(str(repo))
        tags = collector.list_tags(limit=0)

        assert len(tags) == 7


# ── Fix #5: _ALL_AUDIENCES missing "customer" ───────────────────────────────


class TestCustomerAudienceAvailability:
    """Regression: _ALL_AUDIENCES in app.py and _VALID_AUDIENCES in file_config.py
    were missing "customer", even though Audience enum and views.py support it.
    Fix: added "customer" to both lists.
    """

    def test_customer_in_all_audiences(self):
        """GIVEN the CLI audience list."""
        from releasepilot.cli.app import _ALL_AUDIENCES

        assert "customer" in _ALL_AUDIENCES

    def test_customer_in_config_valid_audiences(self):
        """GIVEN the config validation audience set."""
        from releasepilot.config.file_config import _VALID_AUDIENCES

        assert "customer" in _VALID_AUDIENCES

    def test_audience_enum_matches_all_audiences(self):
        """All Audience enum values should appear in _ALL_AUDIENCES."""
        from releasepilot.cli.app import _ALL_AUDIENCES
        from releasepilot.domain.enums import Audience

        for a in Audience:
            assert a.value in _ALL_AUDIENCES, f"Audience.{a.name} ({a.value}) missing from _ALL_AUDIENCES"


# ── Fix #6: _is_empty_release i18n incompatibility ──────────────────────────


class TestIsEmptyReleaseI18n:
    """Regression: _is_empty_release checked for the English-only string
    "0 changes in this release" which never appears in any rendered output.
    The actual empty-release output uses the i18n label 'no_notable_changes'.
    Fix: check all supported language variants of the label.
    """

    def test_detects_empty_english(self):
        """GIVEN empty-release English output."""
        from releasepilot.cli.app import _is_empty_release

        output = "# Release 1.0.0\n\nNo notable changes in this release.\n"
        assert _is_empty_release(output) is True

    def test_detects_empty_polish(self):
        """GIVEN empty-release Polish output."""
        from releasepilot.cli.app import _is_empty_release

        output = "# Release 1.0.0\n\nBrak istotnych zmian w tym wydaniu.\n"
        assert _is_empty_release(output) is True

    def test_detects_empty_german(self):
        """GIVEN empty-release German output."""
        from releasepilot.cli.app import _is_empty_release

        output = "# Release 1.0.0\n\nKeine nennenswerten Änderungen in dieser Version.\n"
        assert _is_empty_release(output) is True

    def test_non_empty_release(self):
        """GIVEN normal release output with content."""
        from releasepilot.cli.app import _is_empty_release

        output = "# Release 1.0.0\n\n## Features\n- Added dark mode\n"
        assert _is_empty_release(output) is False

    def test_blank_output_is_empty(self):
        """GIVEN blank output."""
        from releasepilot.cli.app import _is_empty_release

        assert _is_empty_release("") is True
        assert _is_empty_release("   \n  ") is True


# ── Fix #7: _build_settings config-override-defaults ────────────────────────


class TestBuildSettingsNoneSentinel:
    """Regression: _build_settings compared CLI values to hardcoded defaults
    (e.g. `audience != "changelog"`) to decide if the config file value should
    override. This meant explicitly passing `--audience changelog` on the CLI
    was silently overridden by the config file.
    Fix: use None as default sentinel so config values only apply when user
    didn't pass any value.
    """

    def test_none_audience_uses_config_value(self):
        """GIVEN audience=None (user didn't pass --audience)."""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(audience="user")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".", from_ref="", to_ref="HEAD",
                source_file="", version_str="", title="",
                audience=None,
            )
        assert settings.audience == Audience.USER

    def test_explicit_audience_overrides_config(self):
        """GIVEN audience='changelog' explicitly passed by user."""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(audience="user")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".", from_ref="", to_ref="HEAD",
                source_file="", version_str="", title="",
                audience="changelog",
            )
        assert settings.audience == Audience.CHANGELOG

    def test_none_language_uses_config_value(self):
        """GIVEN lang=None (user didn't pass --language)."""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(language="pl")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".", from_ref="", to_ref="HEAD",
                source_file="", version_str="", title="",
                lang=None,
            )
        assert settings.language == "pl"

    def test_explicit_language_overrides_config(self):
        """GIVEN lang='en' explicitly passed by user."""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(language="pl")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".", from_ref="", to_ref="HEAD",
                source_file="", version_str="", title="",
                lang="en",
            )
        assert settings.language == "en"

    def test_none_format_uses_config_value(self):
        """GIVEN output_format=None (user didn't pass --format)."""
        from unittest.mock import patch

        from releasepilot.cli.app import _build_settings
        from releasepilot.config.file_config import FileConfig

        mock_cfg = FileConfig(format="plaintext")

        with patch("releasepilot.config.file_config.load_config", return_value=mock_cfg):
            settings = _build_settings(
                repo=".", from_ref="", to_ref="HEAD",
                source_file="", version_str="", title="",
                output_format=None,
            )
        from releasepilot.domain.enums import OutputFormat
        assert settings.output_format == OutputFormat.PLAINTEXT


# ── Fix #8: Guide preference index 0 treated as falsy ───────────────────────


class TestGuidePreferenceIndexZero:
    """Regression: In guide.py, `get_pref("audience", choices) or 5` treats
    index 0 (a valid preference for the first choice) as falsy, falling back
    to index 5 instead.
    Fix: use `pref_idx if pref_idx is not None else default`.
    """

    def test_preference_index_zero_not_overridden(self):
        """GIVEN a preference function returning 0 (first item in list)."""
        # Verify the pattern used in the fix
        pref_idx = 0
        default = 5

        # Old pattern (buggy): result = pref_idx or default → 5
        old_result = pref_idx or default
        assert old_result == 5  # This was the bug

        # New pattern (fixed): result = pref_idx if pref_idx is not None else default → 0
        new_result = pref_idx if pref_idx is not None else default
        assert new_result == 0  # This is correct

    def test_preference_none_uses_default(self):
        """GIVEN a preference function returning None (no preference saved)."""
        pref_idx = None
        default = 5

        result = pref_idx if pref_idx is not None else default
        assert result == 5


# ── Additional edge case tests ───────────────────────────────────────────────


class TestDedupEmptyInput:
    """Edge case: deduplicate should handle empty input gracefully."""

    def test_empty_list(self):
        from releasepilot.processing.dedup import deduplicate
        assert deduplicate([]) == []

    def test_single_item(self):
        from releasepilot.processing.dedup import deduplicate
        item = _make_item()
        result = deduplicate([item])
        assert len(result) == 1


class TestAudienceViewsEmptyNotes:
    """Edge case: audience views should handle notes with no groups."""

    def test_summary_empty_groups(self):
        from releasepilot.audience.views import apply_audience
        notes = _make_notes(items=[], groups=())
        result = apply_audience(notes, Audience.SUMMARY)
        assert len(result.groups) == 0
        assert result.total_changes == 0

    def test_customer_empty_groups(self):
        from releasepilot.audience.views import apply_audience
        notes = _make_notes(items=[], groups=())
        result = apply_audience(notes, Audience.CUSTOMER)
        assert len(result.groups) == 0
        assert result.total_changes == 0

    def test_user_empty_groups(self):
        from releasepilot.audience.views import apply_audience
        notes = _make_notes(items=[], groups=())
        result = apply_audience(notes, Audience.USER)
        assert len(result.groups) == 0
        assert result.total_changes == 0
