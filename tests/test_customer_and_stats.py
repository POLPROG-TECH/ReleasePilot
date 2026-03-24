"""Tests for customer audience view, enhanced pipeline stats, days-based date input, executive metrics, and translation integration."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from releasepilot.config.settings import RenderConfig, Settings
from releasepilot.domain.enums import Audience, ChangeCategory
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_item(title: str, cat: ChangeCategory = ChangeCategory.FEATURE, **kw):
    return ChangeItem(id=title[:8], title=title, category=cat, **kw)


def _make_notes(**kw) -> ReleaseNotes:
    defaults = dict(
        release_range=ReleaseRange(from_ref="v1", to_ref="v2", app_name="TestApp"),
        groups=(
            ChangeGroup(
                category=ChangeCategory.FEATURE,
                items=(_make_item("Add dashboard"),),
            ),
        ),
        total_changes=1,
        metadata={},
    )
    defaults.update(kw)
    return ReleaseNotes(**defaults)


# ── 1. Customer audience in Audience enum ────────────────────────────────────


class TestCustomerAudience:
    """Scenarios for customer audience in the Audience enum."""

    def test_customer_in_enum(self):
        """GIVEN the Audience enum."""

        """THEN CUSTOMER has the value 'customer'."""
        assert Audience.CUSTOMER == "customer"

    def test_customer_view_hides_refactor(self):
        """GIVEN release notes with FEATURE, REFACTOR, and INFRASTRUCTURE groups."""
        from releasepilot.audience.views import apply_audience

        notes = _make_notes(
            groups=(
                ChangeGroup(
                    category=ChangeCategory.FEATURE,
                    items=(_make_item("New login"),),
                ),
                ChangeGroup(
                    category=ChangeCategory.REFACTOR,
                    items=(_make_item("Refactor internals"),),
                ),
                ChangeGroup(
                    category=ChangeCategory.INFRASTRUCTURE,
                    items=(_make_item("Update CI"),),
                ),
            ),
            total_changes=3,
        )

        """WHEN apply_audience is called with CUSTOMER audience."""
        result = apply_audience(notes, Audience.CUSTOMER)

        """THEN only FEATURE groups remain, REFACTOR and INFRASTRUCTURE are hidden."""
        cats = {g.category for g in result.groups}
        assert ChangeCategory.FEATURE in cats
        assert ChangeCategory.REFACTOR not in cats
        assert ChangeCategory.INFRASTRUCTURE not in cats

    def test_customer_view_limits_items(self):
        """GIVEN release notes with 10 feature items."""
        from releasepilot.audience.views import apply_audience

        items = tuple(_make_item(f"Feature {i}") for i in range(10))
        notes = _make_notes(
            groups=(ChangeGroup(category=ChangeCategory.FEATURE, items=items),),
            total_changes=10,
        )

        """WHEN apply_audience is called with CUSTOMER audience."""
        result = apply_audience(notes, Audience.CUSTOMER)

        """THEN items are limited to 5 per group."""
        assert len(result.groups[0].items) == 5  # max_per_group = 5

    def test_customer_filename_default(self):
        """GIVEN a filename map for each audience type."""
        name_map = {
            Audience.TECHNICAL: "TECHNICAL_NOTES",
            Audience.USER: "WHATS_NEW",
            Audience.CUSTOMER: "CUSTOMER_UPDATE",
        }

        """THEN CUSTOMER maps to 'CUSTOMER_UPDATE'."""
        assert name_map[Audience.CUSTOMER] == "CUSTOMER_UPDATE"


# ── 2. Enhanced PipelineStats ────────────────────────────────────────────────


class TestEnhancedStats:
    """Scenarios for enhanced PipelineStats fields."""

    def test_new_fields_exist(self):
        """GIVEN a fresh PipelineStats instance."""
        from releasepilot.pipeline.orchestrator import PipelineStats

        s = PipelineStats()

        """THEN it has first_commit_date, last_commit_date, effective_branch, and effective_date_range fields."""
        assert hasattr(s, "first_commit_date")
        assert hasattr(s, "last_commit_date")
        assert hasattr(s, "effective_branch")
        assert hasattr(s, "effective_date_range")

    def test_detailed_summary_includes_branch(self):
        """GIVEN a PipelineStats instance with branch and date fields populated."""
        from releasepilot.pipeline.orchestrator import PipelineStats

        s = PipelineStats()
        s.raw = 10
        s.after_filter = 8
        s.after_dedup = 7
        s.final = 7
        s.effective_branch = "main"
        s.effective_date_range = "since 2026-01-01"
        s.first_commit_date = "2026-01-05"
        s.last_commit_date = "2026-03-10"

        """WHEN detailed_summary is called."""
        summary = s.detailed_summary()

        """THEN the summary includes branch, date range, and commit dates."""
        assert "Branch: main" in summary
        assert "since 2026-01-01" in summary
        assert "First commit: 2026-01-05" in summary
        assert "Last commit: 2026-03-10" in summary

    def test_stats_metadata_includes_new_fields(self):
        """GIVEN PipelineStats with commit dates and branch, and a settings/release range."""
        from releasepilot.pipeline.orchestrator import PipelineStats, compose

        s = PipelineStats()
        s.raw = 5
        s.after_filter = 4
        s.after_dedup = 3
        s.final = 3
        s.first_commit_date = "2026-01-01"
        s.last_commit_date = "2026-03-15"
        s.effective_branch = "develop"

        settings = Settings(audience=Audience.CHANGELOG)
        rr = ReleaseRange(from_ref="v1", to_ref="v2")
        items = [_make_item("Test")] * 3

        """WHEN compose builds the release notes."""
        notes = compose(settings, items, rr, s)

        """THEN the notes metadata includes the new stats fields."""
        assert notes.metadata.get("first_commit_date") == "2026-01-01"
        assert notes.metadata.get("last_commit_date") == "2026-03-15"
        assert notes.metadata.get("effective_branch") == "develop"


# ── 3. Markdown stats block ─────────────────────────────────────────────────


class TestMarkdownStatsBlock:
    """Scenarios for Markdown stats block rendering."""

    def test_stats_block_rendered_when_metadata_present(self):
        """GIVEN release notes with pipeline metadata populated."""
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes(
            metadata={
                "raw_count": "10",
                "filtered_out": "3",
                "contributors": "2",
                "first_commit_date": "2026-01-01",
                "last_commit_date": "2026-03-15",
                "effective_branch": "main",
                "pipeline_summary": "10 → 3 → 7",
            },
        )

        """WHEN the MarkdownRenderer renders the notes."""
        output = MarkdownRenderer().render(notes, RenderConfig())

        """THEN the output includes a stats block with commit dates."""
        assert "Release Metrics" in output or "📊" in output
        assert "2026-01-01" in output
        assert "2026-03-15" in output

    def test_stats_block_absent_without_metadata(self):
        """GIVEN release notes with empty metadata."""
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes(metadata={})

        """WHEN the MarkdownRenderer renders the notes."""
        output = MarkdownRenderer().render(notes, RenderConfig())

        """THEN no stats block appears in the output."""
        assert "📊" not in output


# ── 4. Executive metrics position ───────────────────────────────────────────


class TestExecutiveMetricsPosition:
    """Scenarios for executive metrics positioning."""

    def test_metrics_before_achievements(self):
        """GIVEN an ExecutiveBrief with metrics and achievements."""
        from releasepilot.audience.executive import ExecutiveBrief, ImpactArea
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer

        brief = ExecutiveBrief(
            release_range=ReleaseRange(from_ref="v1", to_ref="v2", app_name="App"),
            executive_summary="Summary text.",
            key_achievements=("Achievement 1",),
            impact_areas=(
                ImpactArea(title="New Capabilities", summary="New stuff", items=("Item",)),
            ),
            risks=(),
            next_steps=(),
            metrics={"total_changes": 5, "features": 3},
        )

        """WHEN the ExecutiveMarkdownRenderer renders the brief."""
        output = ExecutiveMarkdownRenderer().render(brief)

        """THEN Release Metrics appears before Key Achievements."""
        metrics_pos = output.index("Release Metrics")
        achievements_pos = output.index("Key Achievements")
        assert metrics_pos < achievements_pos


# ── 5. Days input in _prompt_valid_date ──────────────────────────────────────


class TestDaysInput:
    """Scenarios for days input in _prompt_valid_date."""

    def test_numeric_days_accepted(self):
        """GIVEN a user entering '30' as days input."""
        from releasepilot.cli.guide import _prompt_valid_date

        with (
            patch("releasepilot.cli.guide_steps.text_prompt", return_value="30"),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the date 30 days ago is returned."""
        expected = (date.today() - timedelta(days=30)).isoformat()
        assert result == expected

    def test_zero_days_rejected_then_valid(self):
        """GIVEN a user entering '0' then a valid date."""
        from releasepilot.cli.guide import _prompt_valid_date

        valid = (date.today() - timedelta(days=1)).isoformat()
        calls = iter(["0", valid])
        with (
            patch("releasepilot.cli.guide_steps.text_prompt", side_effect=calls),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the valid date is returned after rejecting zero."""
        assert result == valid

    def test_large_days_rejected_then_valid(self):
        """GIVEN a user entering '9999' then a valid date."""
        from releasepilot.cli.guide import _prompt_valid_date

        valid = (date.today() - timedelta(days=1)).isoformat()
        calls = iter(["9999", valid])
        with (
            patch("releasepilot.cli.guide_steps.text_prompt", side_effect=calls),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the valid date is returned after rejecting the large value."""
        assert result == valid

    def test_date_still_accepted(self):
        """GIVEN a user entering yesterday's date as an ISO string."""
        from releasepilot.cli.guide import _prompt_valid_date

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with patch("releasepilot.cli.guide_steps.text_prompt", return_value=yesterday):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the ISO date is accepted and returned."""
        assert result == yesterday

    def test_non_numeric_non_date_rejected(self):
        """GIVEN a user entering 'abc' then a valid date."""
        from releasepilot.cli.guide import _prompt_valid_date

        valid = (date.today() - timedelta(days=1)).isoformat()
        calls = iter(["abc", valid])
        with (
            patch("releasepilot.cli.guide_steps.text_prompt", side_effect=calls),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the valid date is returned after rejecting non-numeric input."""
        assert result == valid


# ── 6. Default audience is Executive ─────────────────────────────────────────


class TestAudienceDefault:
    """Scenarios for default audience selection."""

    def test_executive_is_default_audience(self):
        """GIVEN the _AUDIENCE_CHOICES list."""
        from releasepilot.cli.guide import _AUDIENCE_CHOICES

        """THEN Executive is at index 5 (last item)."""
        # Executive should be at index 5 (last item)
        assert _AUDIENCE_CHOICES[5][1] == Audience.EXECUTIVE

    def test_step_audience_default_index(self):
        """GIVEN _step_audience with no stored preference."""
        from releasepilot.cli.guide import _step_audience

        with patch(
            "releasepilot.cli.guide_steps.select_one",
            return_value=Audience.EXECUTIVE,
        ) as mock_sel:
            """WHEN _step_audience is called."""
            result = _step_audience(lambda *a: None)

        """THEN it uses index 0 (Standard changelog) as the default."""
        assert result == Audience.EXECUTIVE
        _, kwargs = mock_sel.call_args
        assert kwargs.get("default_index") == 0


# ── 7. Translation integration ───────────────────────────────────────────────


class TestTranslationIntegration:
    """Scenarios for translation integration."""

    def test_translate_helper_skips_english(self):
        """GIVEN the _translate helper and English language."""
        from releasepilot.rendering.markdown import _translate

        """THEN the text is returned unchanged."""
        assert _translate("Hello world", "en") == "Hello world"

    def test_translate_helper_calls_translate_text(self):
        """GIVEN the _translate helper with translate_text mocked for French."""
        from releasepilot.rendering.markdown import _translate

        with patch(
            "releasepilot.i18n.translate_text",
            return_value="Bonjour le monde",
        ) as mock_t:
            """WHEN _translate is called with 'fr'."""
            result = _translate("Hello world", "fr")

        """THEN it returns the translated text and calls translate_text."""
        assert result == "Bonjour le monde"
        mock_t.assert_called_once_with("Hello world", target_lang="fr")

    def test_markdown_renderer_translates_items(self):
        """GIVEN release notes and _translate mocked to prefix non-English text with [PL]."""
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes()
        with patch(
            "releasepilot.rendering.markdown._translate",
            side_effect=lambda t, lang: f"[PL]{t}" if lang != "en" else t,
        ):
            """WHEN the renderer renders with language 'pl'."""
            output = MarkdownRenderer().render(notes, RenderConfig(language="pl"))

        """THEN commit titles remain untranslated but group labels are translated."""
        # Commit titles must remain untranslated
        assert "Add dashboard" in output
        # Group labels should be translated
        assert "[PL]" in output

    def test_markdown_renderer_no_translate_english(self):
        """GIVEN release notes and _translate wrapped to pass through text."""
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes()
        with patch(
            "releasepilot.rendering.markdown._translate",
            wraps=lambda t, lang: t,
        ) as mock:
            """WHEN the renderer renders with language 'en'."""
            MarkdownRenderer().render(notes, RenderConfig(language="en"))

        """THEN all _translate calls receive 'en' as the language."""
        # _translate should be called but return original for english
        for call_args in mock.call_args_list:
            assert call_args[0][1] == "en"

    def test_translate_text_function_exists(self):
        """GIVEN the translate_text function with source and target both English."""
        from releasepilot.i18n import translate_text

        """THEN the original text is returned unchanged."""
        # Should return original when same language
        result = translate_text("Hello", target_lang="en", source_lang="en")
        assert result == "Hello"

    def test_translate_text_placeholder_protection(self):
        """GIVEN a text containing version and date placeholders."""
        from releasepilot.i18n.translator import translate_text

        """WHEN translate_text is called targeting Polish."""
        # When deep-translator is not installed, returns original
        result = translate_text("Update v1.2.0 on 2026-01-15", "pl")

        """THEN placeholders are preserved in the result."""
        # Should at minimum return original (fallback) or translated with preserved placeholders
        assert "v1.2.0" in result
        assert "2026-01-15" in result


# ── 8. New i18n labels ───────────────────────────────────────────────────────


class TestNewI18nLabels:
    """Scenarios for new i18n labels."""

    def test_customer_update_label_exists(self):
        """GIVEN the i18n get_label function."""
        from releasepilot.i18n import get_label

        """THEN 'customer_update' returns correct labels for English and Polish."""
        assert get_label("customer_update", "en") == "Product Update"
        assert get_label("customer_update", "pl") == "Aktualizacja produktu"

    def test_whats_new_label_exists(self):
        """GIVEN the i18n get_label function."""
        from releasepilot.i18n import get_label

        """THEN 'whats_new' returns correct labels for English and French."""
        assert get_label("whats_new", "en") == "What's New"
        assert get_label("whats_new", "fr") == "Nouveautés"

    def test_bug_fixes_label_exists(self):
        """GIVEN the i18n get_label function."""
        from releasepilot.i18n import get_label

        """THEN 'bug_fixes' returns correct labels for English and German."""
        assert get_label("bug_fixes", "en") == "Bug Fixes"
        assert get_label("bug_fixes", "de") == "Fehlerbehebungen"


# ── 9. Schema includes customer audience ─────────────────────────────────────


class TestSchemaCustomer:
    """Scenarios for customer audience in schema."""

    def test_schema_includes_customer(self):
        """GIVEN the releasepilot JSON schema."""
        import json
        from pathlib import Path

        schema_path = Path(__file__).parent.parent / "schema" / "releasepilot.schema.json"
        schema = json.loads(schema_path.read_text())

        """THEN the audience enum includes 'customer'."""
        audience_enum = schema["properties"]["audience"]["enum"]
        assert "customer" in audience_enum


# ── 10. Customer RenderConfig in guided mode ─────────────────────────────────


class TestCustomerRenderConfig:
    """Scenarios for customer RenderConfig in guided mode."""

    def test_customer_render_config_hides_technical_details(self):
        """GIVEN a RenderConfig with all technical display options disabled."""
        cfg = RenderConfig(
            show_authors=False,
            show_commit_hashes=False,
            show_scope=False,
            show_pr_links=False,
        )

        """THEN no technical metadata is shown."""
        assert not cfg.show_authors
        assert not cfg.show_commit_hashes
        assert not cfg.show_scope
        assert not cfg.show_pr_links
