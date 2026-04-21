"""Tests for title/subtitle composition, ReleaseRange.app_name, audience-aware filenames, and translation label completeness."""

from __future__ import annotations

from datetime import date

import pytest

from releasepilot.config.settings import RenderConfig, Settings
from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
)
from releasepilot.i18n.labels import get_label
from releasepilot.pipeline.orchestrator import _compose_title, build_release_range
from releasepilot.rendering.markdown import MarkdownRenderer

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_settings(**overrides) -> Settings:
    defaults = {"repo_path": "."}
    defaults.update(overrides)
    return Settings(**defaults)


def _make_notes(
    *,
    app_name: str = "",
    title: str = "Changes since 2025-01-01",
    version: str = "",
) -> ReleaseNotes:
    item = ChangeItem(
        id="abc123",
        title="Fix login bug",
        category=ChangeCategory.BUGFIX,
    )
    rr = ReleaseRange(
        from_ref="2025-01-01",
        to_ref="main",
        title=title,
        app_name=app_name,
        version=version,
        release_date=date(2025, 3, 16) if version else None,
    )
    group = ChangeGroup(category=ChangeCategory.BUGFIX, items=(item,))
    return ReleaseNotes(
        release_range=rr,
        highlights=(),
        breaking_changes=(),
        groups=(group,),
        total_changes=1,
        metadata={},
    )


# ── 1. Overwrite default ────────────────────────────────────────────────────


class TestOverwriteDefault:
    """Scenarios for overwrite being the first (default) option."""

    """GIVEN the _confirm_overwrite_or_rename source code"""

    def test_overwrite_is_default_option(self):
        """WHEN the test exercises overwrite is default option"""
        import inspect

        from releasepilot.cli.guide import _confirm_overwrite_or_rename

        source = inspect.getsource(_confirm_overwrite_or_rename)

        """THEN default_index=0 is present, making overwrite the default"""
        assert "default_index=0" in source


# ── 2. Translation labels ───────────────────────────────────────────────────


class TestTranslationLabels:
    """Scenarios for i18n labels across supported languages."""

    """GIVEN the English footer_generated label"""

    def test_footer_generated_label_exists(self):
        """WHEN the test exercises footer generated label exists"""
        label = get_label("footer_generated", "en")

        """THEN it contains {tool} and {author} placeholders"""
        assert "{tool}" in label
        assert "{author}" in label

    """GIVEN the English changes_range label"""

    def test_changes_range_label_exists(self):
        """WHEN the test exercises changes range label exists"""
        label = get_label("changes_range", "en")

        """THEN it contains the {from_date} placeholder"""
        assert "{from_date}" in label

    """GIVEN the footer_generated label for a non-English language"""

    @pytest.mark.parametrize("lang", ["pl", "de", "fr", "es", "it", "pt", "nl", "uk", "cs"])
    def test_footer_generated_translated(self, lang):
        """WHEN the test exercises footer generated translated"""
        label = get_label("footer_generated", lang)

        """THEN it differs from the English version"""
        assert label != get_label("footer_generated", "en")

    """GIVEN the highlights label for a non-English language"""

    @pytest.mark.parametrize("lang", ["pl", "de", "fr", "es"])
    def test_highlights_translated(self, lang):
        """WHEN the test exercises highlights translated"""
        label = get_label("highlights", lang)

        """THEN it is non-empty"""
        assert label  # Non-empty


# ── 3. ReleaseRange.app_name and subtitle ────────────────────────────────────


class TestReleaseRangeAppName:
    """Scenarios for ReleaseRange storing app_name separately from subtitle."""

    """GIVEN a ReleaseRange with app_name set"""

    def test_app_name_stored(self):
        """WHEN the test exercises app name stored"""
        rr = ReleaseRange(from_ref="v1", to_ref="v2", app_name="LoopIt")

        """THEN app_name is stored correctly"""
        assert rr.app_name == "LoopIt"

    """GIVEN a ReleaseRange with both app_name and title"""

    def test_display_title_includes_app_name(self):
        """WHEN the test exercises display title includes app name"""
        rr = ReleaseRange(
            from_ref="v1",
            to_ref="v2",
            app_name="LoopIt",
            title="Monthly Release",
        )

        """THEN display_title combines app_name and title with an em dash"""
        assert rr.display_title == "LoopIt - Monthly Release"

    """GIVEN a ReleaseRange with both app_name and title"""

    def test_subtitle_excludes_app_name(self):
        """WHEN the test exercises subtitle excludes app name"""
        rr = ReleaseRange(
            from_ref="v1",
            to_ref="v2",
            app_name="LoopIt",
            title="Monthly Release",
        )

        """THEN subtitle returns only the title without app_name"""
        assert rr.subtitle == "Monthly Release"

    """GIVEN a ReleaseRange with a version but no title"""

    def test_subtitle_without_title(self):
        """WHEN the test exercises subtitle without title"""
        rr = ReleaseRange(from_ref="v1", to_ref="v2", version="3.0.0")

        """THEN subtitle falls back to 'Release <version>'"""
        assert rr.subtitle == "Release 3.0.0"

    """GIVEN a ReleaseRange with no title and no version"""

    def test_subtitle_fallback_to_refs(self):
        """WHEN the test exercises subtitle fallback to refs"""
        rr = ReleaseRange(from_ref="v1", to_ref="v2")

        """THEN subtitle falls back to the ref range"""
        assert rr.subtitle == "v1..v2"

    """GIVEN a ReleaseRange with a title but no app_name"""

    def test_display_title_no_app_name(self):
        """WHEN the test exercises display title no app name"""
        rr = ReleaseRange(from_ref="v1", to_ref="v2", title="My Title")

        """THEN display_title is just the title"""
        assert rr.display_title == "My Title"


# ── 4. _compose_title no longer includes app_name ────────────────────────────


class TestComposeTitlePhase16:
    """Scenarios for _compose_title returning only the subtitle portion."""

    """GIVEN settings with an app_name"""

    def test_no_app_name_in_result(self):
        s = _make_settings(app_name="LoopIt")

        """WHEN _compose_title is called with a fallback string"""
        result = _compose_title(s, "Changes since 2025-01-01")

        """THEN the result excludes app_name and contains the fallback"""
        assert "LoopIt" not in result
        assert "Changes since 2025-01-01" in result

    """GIVEN settings with an explicit title"""

    def test_title_used_over_fallback(self):
        s = _make_settings(title="Sprint 5 Notes")

        """WHEN _compose_title is called with a fallback string"""
        result = _compose_title(s, "fallback text")

        """THEN the explicit title is used instead of the fallback"""
        assert result == "Sprint 5 Notes"


# ── 5. build_release_range populates app_name ────────────────────────────────


class TestBuildReleaseRangeAppName:
    """Scenarios for build_release_range populating app_name."""

    """GIVEN settings with an explicit app_name"""

    def test_app_name_from_settings(self):
        s = _make_settings(
            app_name="LoopIt",
            since_date="2025-01-01",
            branch="main",
        )

        """WHEN build_release_range is called"""
        rr = build_release_range(s)

        """THEN app_name comes from the settings"""
        assert rr.app_name == "LoopIt"

    """GIVEN settings with no app_name but a repo_path"""

    def test_app_name_from_repo_path(self):
        s = _make_settings(
            repo_path="/tmp/SomeProject",
            since_date="2025-01-01",
            branch="main",
        )

        """WHEN build_release_range is called"""
        rr = build_release_range(s)

        """THEN app_name is inferred from the repo directory name"""
        assert rr.app_name == "SomeProject"


# ── 6. Markdown renderer title structure ─────────────────────────────────────


class TestMarkdownTitleStructure:
    """Scenarios for app name appearing on its own line in markdown output."""

    """GIVEN release notes with an app_name and title"""

    def test_app_name_separate_heading(self):
        notes = _make_notes(app_name="LoopIt", title="Monthly Release")
        config = RenderConfig()

        """WHEN the markdown is rendered"""
        output = MarkdownRenderer().render(notes, config)

        """THEN app_name is an H1 and title is an H2"""
        assert "# LoopIt" in output
        assert "## Monthly Release" in output

    """GIVEN release notes with a title but no app_name"""

    def test_no_app_name_single_heading(self):
        notes = _make_notes(title="Monthly Release")
        config = RenderConfig()

        """WHEN the markdown is rendered"""
        output = MarkdownRenderer().render(notes, config)

        """THEN the title is the single H1 heading"""
        assert "# Monthly Release" in output


# ── 7. Audience-aware default filename ───────────────────────────────────────


class TestAudienceAwareFilename:
    """Scenarios for _step_display_and_export using audience-aware filenames."""

    """GIVEN the _step_display_and_export source code"""

    def test_technical_filename(self):
        """WHEN the test exercises technical filename"""
        import inspect

        from releasepilot.cli.guide import _step_display_and_export

        source = inspect.getsource(_step_display_and_export)

        """THEN it references all audience-aware filename constants"""
        assert "TECHNICAL_NOTES" in source
        assert "WHATS_NEW" in source
        assert "RELEASE_SUMMARY" in source
        assert "CHANGELOG" in source


# ── _compose_title empty-title handling ──────────────────────────


class TestComposeTitleEmpty:
    """Regression tests for _compose_title when title/fallback are empty."""

    """GIVEN empty title and fallback with a version"""

    def test_empty_title_version_only(self):
        s = _make_settings(version="2.1.0")

        """WHEN _compose_title is called with empty fallback"""
        result = _compose_title(s, "")

        """THEN result is 'Version X.Y.Z' with no leading space or em-dash"""
        assert result == "Version 2.1.0"

    """GIVEN a title and version"""

    def test_title_with_version(self):
        s = _make_settings(title="MyApp", version="1.0")

        """WHEN _compose_title is called"""
        result = _compose_title(s, "")

        """THEN result is 'MyApp - Version 1.0'"""
        assert result == "MyApp - Version 1.0"
