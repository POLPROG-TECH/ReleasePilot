"""Tests for internationalization: i18n labels, translator fallback, and multilingual rendering."""

from __future__ import annotations

from datetime import date

import pytest

from releasepilot.config.settings import RenderConfig, Settings
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)
from releasepilot.i18n import SUPPORTED_LANGUAGES, get_label, get_labels_for
from releasepilot.i18n.labels import _LABELS
from releasepilot.pipeline.orchestrator import _compose_title

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_settings(**overrides) -> Settings:
    defaults = {
        "repo_path": ".",
        "since_date": "2025-01-01",
        "branch": "main",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _sample_notes(title: str = "") -> ReleaseNotes:
    from releasepilot.domain.enums import ChangeCategory

    rr = ReleaseRange(
        from_ref="2025-01-01",
        to_ref="main",
        version="1.0.0",
        title=title,
        release_date=date(2025, 6, 1),
    )
    item = ChangeItem(
        id="test-1",
        title="Add user auth",
        category=ChangeCategory.FEATURE,
        source=SourceReference(commit_hash="abc1234"),
    )
    group = ChangeGroup(
        category=ChangeCategory.FEATURE,
        items=(item,),
    )
    return ReleaseNotes(
        release_range=rr,
        groups=(group,),
        highlights=(),
        breaking_changes=(),
        total_changes=1,
    )


# ── Title composition tests ─────────────────────────────────────────────────


class TestComposeTitle:
    """Scenarios for _compose_title logic with title / version combos."""

    """GIVEN settings with no explicit title"""

    def test_fallback_only(self):
        s = _make_settings()

        """WHEN composing a title with a fallback string"""
        result = _compose_title(s, "Changes since 2025-01-01")

        """THEN the fallback string is returned"""
        assert result == "Changes since 2025-01-01"

    """GIVEN settings with an app_name but no explicit title"""

    def test_app_name_not_in_subtitle(self):
        s = _make_settings(app_name="Loudly")

        """WHEN composing a title"""
        result = _compose_title(s, "Changes since 2025-01-01")

        """THEN the subtitle contains the fallback and excludes app_name"""
        assert "Changes since 2025-01-01" in result
        # app_name is on ReleaseRange, not in the composed subtitle
        assert "Loudly" not in result

    """GIVEN settings with an explicit title"""

    def test_explicit_title_used(self):
        s = _make_settings(title="Monthly Update")

        """WHEN composing a title"""
        result = _compose_title(s, "fallback")

        """THEN the explicit title is used and fallback is ignored"""
        assert "Monthly Update" in result
        assert "fallback" not in result

    """GIVEN settings with both app_name and title"""

    def test_title_without_app_prefix(self):
        s = _make_settings(app_name="Loudly", title="Q1 Summary")

        """WHEN composing a title"""
        result = _compose_title(s, "fallback")

        """THEN only the title is returned without app_name prefix"""
        assert result == "Q1 Summary"

    """GIVEN settings with app_name and version but no title"""

    def test_version_appended(self):
        s = _make_settings(app_name="Loudly", version="2.0.0")

        """WHEN composing a title"""
        result = _compose_title(s, "Changes since 2025-01-01")

        """THEN the version is appended to the result"""
        assert "Version 2.0.0" in result

    """GIVEN settings where the title already contains the version string"""

    def test_version_not_duplicated(self):
        s = _make_settings(title="Release 2.0.0", version="2.0.0")

        """WHEN composing a title"""
        result = _compose_title(s, "fallback")

        """THEN the version appears only once"""
        assert result.count("2.0.0") == 1

    """GIVEN settings with app_name, title, and version"""

    def test_title_version(self):
        s = _make_settings(app_name="Loudly", title="Monthly Release", version="3.1.0")

        """WHEN composing a title"""
        result = _compose_title(s, "fallback")

        """THEN the result includes both title and version"""
        assert "Monthly Release" in result
        assert "Version 3.1.0" in result


# ── Settings fields ─────────────────────────────────────────────────────────


class TestSettingsNewFields:
    """Scenarios for Settings and RenderConfig default fields."""

    """GIVEN a default Settings instance"""

    def test_app_name_default_empty(self):
        s = Settings()

        """WHEN inspecting app_name"""

        """THEN it defaults to an empty string"""
        assert s.app_name == ""

    """GIVEN a default Settings instance"""

    def test_language_default_en(self):
        s = Settings()

        """WHEN inspecting language"""

        """THEN it defaults to English"""
        assert s.language == "en"

    """GIVEN a RenderConfig with language set to Polish"""

    def test_render_config_language(self):
        rc = RenderConfig(language="pl")

        """WHEN inspecting language"""

        """THEN it returns the configured language"""
        assert rc.language == "pl"


# ── i18n label tests ────────────────────────────────────────────────────────


class TestI18nLabels:
    """Scenarios for i18n label retrieval and completeness."""

    """GIVEN the SUPPORTED_LANGUAGES set"""

    def test_supported_languages(self):
        """WHEN inspecting its size and contents"""

        """THEN it contains exactly 10 languages including en, pl, and uk"""
        assert len(SUPPORTED_LANGUAGES) == 10
        assert "en" in SUPPORTED_LANGUAGES
        assert "pl" in SUPPORTED_LANGUAGES
        assert "uk" in SUPPORTED_LANGUAGES

    """GIVEN the i18n label system"""

    def test_get_label_english(self):
        """WHEN requesting the 'highlights' label in English"""

        """THEN it returns 'Highlights'"""
        assert get_label("highlights", "en") == "Highlights"

    """GIVEN the i18n label system"""

    def test_get_label_polish(self):
        """WHEN requesting the 'highlights' label in Polish"""

        """THEN it returns the Polish translation"""
        assert get_label("highlights", "pl") == "Najważniejsze"

    """GIVEN an unsupported language code"""

    def test_get_label_fallback_to_english(self):
        """WHEN requesting a label with that language"""
        result = get_label("highlights", "xx")  # unsupported lang

        """THEN it falls back to the English translation"""
        assert result == "Highlights"

    """GIVEN a nonexistent label key"""

    def test_get_label_unknown_key(self):
        """WHEN requesting that label"""
        result = get_label("nonexistent_key", "en")

        """THEN the key itself is returned as fallback"""
        assert result == "nonexistent_key"

    """GIVEN the full _LABELS dictionary and SUPPORTED_LANGUAGES set"""

    def test_all_labels_have_all_languages(self):
        """WHEN checking every label key against every supported language"""

        """THEN every label has translations for all supported languages"""
        for key, translations in _LABELS.items():
            for lang in SUPPORTED_LANGUAGES:
                assert lang in translations, f"Missing {lang} for label '{key}'"

    """GIVEN the i18n label system"""

    def test_get_labels_for_returns_dict(self):
        """WHEN requesting all labels for German"""
        labels = get_labels_for("de")

        """THEN a dict is returned containing the expected translations"""
        assert isinstance(labels, dict)
        assert "highlights" in labels
        assert labels["highlights"] == "Highlights"  # German uses same word

    """GIVEN the i18n label system"""

    def test_changes_in_release_has_placeholder(self):
        """WHEN requesting the 'changes_in_release' label in English"""
        label = get_label("changes_in_release", "en")

        """THEN it contains a {count} placeholder"""
        assert "{count}" in label

    """GIVEN the i18n label system"""

    def test_released_on_has_placeholder(self):
        """WHEN requesting the 'released_on' label in English"""
        label = get_label("released_on", "en")

        """THEN it contains a {date} placeholder"""
        assert "{date}" in label

    """GIVEN the 'changes_in_release' label for a supported language"""

    @pytest.mark.parametrize("lang", list(SUPPORTED_LANGUAGES))
    def test_changes_in_release_format_works(self, lang: str):
        label = get_label("changes_in_release", lang)

        """WHEN formatting it with count=42"""
        formatted = label.format(count=42)

        """THEN the formatted string contains '42'"""
        assert "42" in formatted


# ── i18n translator tests ───────────────────────────────────────────────────


class TestTranslator:
    """Scenarios for i18n translator behaviour."""

    """GIVEN the translate_text function"""

    def test_same_language_returns_original(self):
        from releasepilot.i18n.translator import translate_text

        """WHEN translating text from English to English"""

        """THEN the original text is returned unchanged"""
        assert translate_text("Hello world", "en", "en") == "Hello world"

    """GIVEN the translate_text function"""

    def test_empty_text_returns_original(self):
        from releasepilot.i18n.translator import translate_text

        """WHEN translating empty or whitespace-only text"""

        """THEN the original text is returned unchanged"""
        assert translate_text("", "pl") == ""
        assert translate_text("   ", "pl") == "   "

    """GIVEN the translate_text function (deep-translator may be absent)"""

    def test_fallback_on_missing_dependency(self):
        from releasepilot.i18n.translator import translate_text

        """WHEN translating text to Polish"""
        # This should not raise even if deep-translator is absent
        result = translate_text("test text", "pl")

        """THEN a string is returned without raising"""
        assert isinstance(result, str)


# ── Markdown renderer i18n tests ────────────────────────────────────────────


class TestMarkdownI18n:
    """Scenarios for Markdown renderer i18n headings."""

    """GIVEN sample release notes and an English render config"""

    def test_english_headings(self):
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _sample_notes(title="Test Release")
        config = RenderConfig(language="en")

        """WHEN rendering to Markdown"""
        output = MarkdownRenderer().render(notes, config)

        """THEN the output contains English headings"""
        assert "changes in this release" in output

    """GIVEN sample release notes and a Polish render config"""

    def test_polish_headings(self):
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _sample_notes(title="Test Release")
        config = RenderConfig(language="pl")

        """WHEN rendering to Markdown"""
        output = MarkdownRenderer().render(notes, config)

        """THEN the output contains Polish headings"""
        assert "Zmian w tym wydaniu:" in output

    """GIVEN sample release notes and a German render config"""

    def test_german_headings(self):
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _sample_notes(title="Test Release")
        config = RenderConfig(language="de")

        """WHEN rendering to Markdown"""
        output = MarkdownRenderer().render(notes, config)

        """THEN the output contains German headings"""
        assert "Änderungen in dieser Version" in output

    """GIVEN an empty release and a Polish render config"""

    def test_empty_release_translated(self):
        from releasepilot.rendering.markdown import MarkdownRenderer

        rr = ReleaseRange(from_ref="a", to_ref="b", title="Empty")
        notes = ReleaseNotes(
            release_range=rr,
            groups=(),
            highlights=(),
            breaking_changes=(),
        )
        config = RenderConfig(language="pl")

        """WHEN rendering to Markdown"""
        output = MarkdownRenderer().render(notes, config)

        """THEN the output contains the Polish 'no changes' message"""
        assert "Brak istotnych zmian" in output
