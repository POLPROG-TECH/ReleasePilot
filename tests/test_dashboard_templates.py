"""Tests for the ReleasePilot dashboard package."""

from __future__ import annotations

import json
import re

import pytest

from releasepilot.dashboard.reporter import HtmlReporter
from releasepilot.dashboard.schema import (
    ArtifactPreview,
    CategoryDistribution,
    ChangeEntry,
    ChangeGroupData,
    DashboardData,
    PipelineStageStats,
)

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_change() -> ChangeEntry:
    return ChangeEntry(
        hash="abc12345",
        title="Add user authentication",
        category="feature",
        category_emoji="✨",
        scope="auth",
        authors=("alice", "bob"),
        date="2025-03-20",
        importance="high",
        breaking=False,
        pr_number=42,
        source="git",
    )


@pytest.fixture
def sample_data(sample_change: ChangeEntry) -> DashboardData:
    return DashboardData(
        repo_path="/home/user/myapp",
        branch="main",
        from_ref="v1.0.0",
        to_ref="HEAD",
        version="1.1.0",
        app_name="MyApp",
        total_changes=5,
        changes=(
            sample_change,
            ChangeEntry(
                hash="def67890",
                title="Fix login crash",
                category="bugfix",
                category_emoji="🐛",
                scope="auth",
                authors=("charlie",),
                date="2025-03-21",
                importance="normal",
                breaking=False,
            ),
            ChangeEntry(
                hash="ghi11111",
                title="Drop legacy API",
                category="breaking",
                category_emoji="⚠️",
                scope="api",
                authors=("alice",),
                date="2025-03-22",
                importance="high",
                breaking=True,
            ),
            ChangeEntry(
                hash="jkl22222",
                title="Improve startup time",
                category="performance",
                category_emoji="⚡",
                scope="core",
                authors=("dave",),
                date="2025-03-22",
                importance="normal",
                breaking=False,
            ),
            ChangeEntry(
                hash="mno33333",
                title="Update README",
                category="documentation",
                category_emoji="📝",
                scope="",
                authors=("eve",),
                date="2025-03-22",
                importance="low",
                breaking=False,
            ),
        ),
        pipeline_stats=(
            PipelineStageStats("collected", 10, 10),
            PipelineStageStats("classified", 10, 10),
            PipelineStageStats("filtered", 10, 7),
            PipelineStageStats("deduplicated", 7, 5),
        ),
        category_distribution=(
            CategoryDistribution("feature", "✨", 1, 20.0),
            CategoryDistribution("bugfix", "🐛", 1, 20.0),
            CategoryDistribution("breaking", "⚠️", 1, 20.0),
            CategoryDistribution("performance", "⚡", 1, 20.0),
            CategoryDistribution("documentation", "📝", 1, 20.0),
        ),
        highlights=(sample_change,),
        breaking_changes=(
            ChangeEntry(
                hash="ghi11111",
                title="Drop legacy API",
                category="breaking",
                category_emoji="⚠️",
                scope="api",
                authors=("alice",),
                date="2025-03-22",
                importance="high",
                breaking=True,
            ),
        ),
        groups=(ChangeGroupData("feature", "✨", 1, (sample_change,)),),
        artifacts=(
            ArtifactPreview(
                audience="changelog",
                format="markdown",
                content="# MyApp v1.1.0\n\n## Features\n- Add user auth",
                size_bytes=48,
            ),
        ),
        generated_at="2025-03-22T12:00:00",
        language="en",
        audience="changelog",
        output_format="markdown",
    )


@pytest.fixture
def empty_data() -> DashboardData:
    return DashboardData(
        repo_path="/tmp/empty",
        diagnostics=("No git tags found", "Try specifying --from and --to"),
        directory_exists=True,
        generated_at="2025-03-22T12:00:00",
    )


@pytest.fixture
def reporter() -> HtmlReporter:
    return HtmlReporter()


# ── Schema Tests ──────────────────────────────────────────────────────────


# ── Reporter Tests ────────────────────────────────────────────────────────


# ── Template Structure Tests ──────────────────────────────────────────────


# ── Wizard & Guide Tests ─────────────────────────────────────────────────


# ── Use Case Tests ────────────────────────────────────────────────────────


class TestTemplateStructure:
    """Verify the HTML template has the correct structure."""

    """GIVEN a scenario for has theme support"""
    def test_has_theme_support(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has theme support"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has theme support is observed"""
        assert 'data-theme="light"' in html
        assert '[data-theme="dark"]' in html
        assert '[data-theme="midnight"]' in html

    """GIVEN a scenario for has tabs"""
    def test_has_tabs(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has tabs"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has tabs is observed"""
        assert 'data-tab="generate"' in html
        assert 'data-tab="changes"' in html
        assert 'data-tab="artifacts"' in html
        assert 'data-tab="guide"' in html
        # Overview tab was removed - generate is the default
        assert 'data-tab="overview"' not in html

    """GIVEN a scenario for has settings panel"""
    def test_has_settings_panel(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has settings panel"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has settings panel is observed"""
        assert 'id="qsPanel"' in html
        assert "applyTheme" in html
        assert "applyLocale" in html
        assert "applyDensity" in html
        # Settings trigger button must have onclick
        assert 'id="qsTrigger"' in html
        assert 'onclick="toggleQS()"' in html

    """GIVEN a scenario for has i18n"""
    def test_has_i18n(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has i18n"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has i18n is observed"""
        assert "data-i18n=" in html
        assert "I18N" in html
        assert '"ui.tab.generate"' in html
        assert '"ui.tab.changes"' in html

    """GIVEN a scenario for has first run"""
    def test_has_first_run(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has first run"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has first run is observed"""
        assert "first-run-panel" in html
        assert "first-run-action" in html

    """GIVEN a scenario for has accessibility"""
    def test_has_accessibility(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has accessibility"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has accessibility is observed"""
        assert 'class="skip-link"' in html
        assert 'role="tablist"' in html
        assert 'role="tab"' in html
        assert 'role="tabpanel"' in html
        assert "aria-selected" in html
        # Tab buttons have SVG icons (LocaleSync pattern)
        assert "<svg" in html

    """GIVEN a scenario for has modal"""
    def test_has_modal(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has modal"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has modal is observed"""
        assert "modalOverlay" in html
        assert "openModal" in html
        assert "closeModal" in html

    """GIVEN a scenario for has responsive styles"""
    def test_has_responsive_styles(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises has responsive styles"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has responsive styles is observed"""
        assert "@media(max-width:768px)" in html
        assert "@media(max-width:480px)" in html

    """GIVEN a scenario for localstorage safe"""
    def test_localstorage_safe(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises localstorage safe"""
        html = reporter.render(sample_data)
        js = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
        """THEN the expected behavior for localstorage safe is observed"""
        assert "function _ls(" in js
        assert "function _ss(" in js
        # No raw localStorage.setItem outside the helper
        raw_count = js.count("localStorage.setItem")
        assert raw_count <= 1, f"Found {raw_count} raw localStorage.setItem calls"

    """GIVEN a scenario for clipboard has catch"""
    def test_clipboard_has_catch(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises clipboard has catch"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for clipboard has catch is observed"""
        assert ".catch(function" in html

    """GIVEN a scenario for has reduced motion"""
    def test_has_reduced_motion(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has reduced motion"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has reduced motion is observed"""
        assert "prefers-reduced-motion" in html

    """GIVEN a scenario for has print styles"""
    def test_has_print_styles(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has print styles"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has print styles is observed"""
        assert "@media print" in html

    """GIVEN a scenario for has footer"""
    def test_has_footer(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has footer"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has footer is observed"""
        assert "POLPROG" in html
        assert "ReleasePilot" in html
        assert "app-footer-copyright" in html
        assert "app-footer-tools" in html
        assert "app-footer-author" in html
        assert "app-footer-brand" in html
        assert "polprog.pl" in html
        assert "All rights reserved" in html

    """GIVEN a scenario for has escape function"""
    def test_has_escape_function(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has escape function"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has escape function is observed"""
        assert "function esc(" in html


class TestWizardAndGuide:
    """Verify the wizard, guide, export, and preview UI elements exist."""

    """GIVEN a scenario for has wizard panel"""
    def test_has_wizard_panel(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has wizard panel"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has wizard panel is observed"""
        assert 'id="panel-generate"' in html
        assert "wizard-steps" in html
        assert "wizard-panel" in html

    """GIVEN a scenario for has wizard steps"""
    def test_has_wizard_steps(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has wizard steps"""
        html = reporter.render(sample_data)
        # All 6 steps
        for i in range(6):
            assert f'id="wiz-panel-{i}"' in html

    """GIVEN a scenario for has wizard audience selection"""
    def test_has_wizard_audience_selection(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises has wizard audience selection"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has wizard audience selection is observed"""
        assert "wiz-audience-options" in html
        assert "AUDIENCE_INFO" in html
        assert "wizSelectAudience" in html

    """GIVEN a scenario for has wizard format selection"""
    def test_has_wizard_format_selection(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises has wizard format selection"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has wizard format selection is observed"""
        assert "wiz-format-options" in html
        assert "FORMAT_INFO" in html
        assert "wizSelectFormat" in html

    """GIVEN a scenario for has wizard preview"""
    def test_has_wizard_preview(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has wizard preview"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has wizard preview is observed"""
        assert "wiz-preview-area" in html
        assert "wizCopyPreview" in html
        assert "wizard-preview-area" in html

    """GIVEN a scenario for has wizard export"""
    def test_has_wizard_export(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has wizard export"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has wizard export is observed"""
        assert "wiz-export-audience" in html
        assert "wiz-export-format" in html
        assert "wiz-export-filename" in html
        assert "wizDoExport" in html

    """GIVEN a scenario for has wizard navigation"""
    def test_has_wizard_navigation(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises has wizard navigation"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has wizard navigation is observed"""
        assert "wizard-footer" in html
        assert "wiz-prev-btn" in html
        assert "wiz-next-btn" in html
        assert "wizPrev" in html
        assert "wizNext" in html

    """GIVEN a scenario for has wizard generate step"""
    def test_has_wizard_generate_step(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises has wizard generate step"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has wizard generate step is observed"""
        assert "wiz-progress" in html
        assert "wizard-progress-spinner" in html
        assert "wiz-generate-result" in html

    """GIVEN a scenario for has guide panel"""
    def test_has_guide_panel(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has guide panel"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has guide panel is observed"""
        assert 'id="panel-guide"' in html
        assert "guide-content" in html
        assert "renderGuide" in html

    """GIVEN a scenario for has guide sections"""
    def test_has_guide_sections(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has guide sections"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has guide sections is observed"""
        assert "guide-hero" in html
        assert "guide-pipeline" in html
        assert "guide-cards" in html
        assert "guide-cli-ref" in html

    """GIVEN a scenario for has export modal"""
    def test_has_export_modal(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises has export modal"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has export modal is observed"""
        assert "exportModalOverlay" in html
        assert "export-audience" in html
        assert "export-format" in html
        assert "export-filename" in html
        assert "openExportModal" in html
        assert "doExportFromModal" in html

    """GIVEN a scenario for has artifact filtering"""
    def test_has_artifact_filtering(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises has artifact filtering"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has artifact filtering is observed"""
        assert "artifact-aud-filter" in html
        assert "artifact-fmt-filter" in html
        assert "audienceFilter" in html

    """GIVEN a scenario for has launch wizard action"""
    def test_has_launch_wizard_action(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises has launch wizard action"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has launch wizard action is observed"""
        assert "launchWizard" in html

    """GIVEN First-run panel should not show raw CLI commands as primary UX"""
    def test_first_run_no_cli_commands(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises first run no cli commands"""
        html = reporter.render(sample_data)
        # The first-run section should not contain releasepilot commands
        first_run_match = re.search(
            r'id="first-run-panel".*?</div>\s*</div>\s*</div>',
            html,
            re.DOTALL,
        )
        if first_run_match:
            first_run_html = first_run_match.group(0)
            assert "releasepilot generate" not in first_run_html
            assert "releasepilot dashboard" not in first_run_html

    """GIVEN a scenario for has find artifact function"""
    def test_has_find_artifact_function(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises has find artifact function"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for has find artifact function is observed"""
        assert "function findArtifact(" in html

    """GIVEN a scenario for wizard i18n keys"""
    def test_wizard_i18n_keys(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises wizard i18n keys"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for wizard i18n keys is observed"""
        assert '"ui.tab.generate"' in html
        assert '"ui.tab.guide"' in html
        assert '"ui.wizard.source"' in html
        assert '"ui.wizard.audience"' in html
        assert '"ui.wizard.format"' in html
        assert '"ui.wizard.preview"' in html
        assert '"ui.wizard.export_step"' in html
        assert '"ui.guide.hero_title"' in html

    """GIVEN a scenario for wizard i18n polish"""
    def test_wizard_i18n_polish(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises wizard i18n polish"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for wizard i18n polish is observed"""
        assert '"ui.tab.generate":"Generuj"' in html or '"ui.tab.generate": "Generuj"' in html
        assert '"ui.tab.guide":"Przewodnik"' in html or '"ui.tab.guide": "Przewodnik"' in html

    """GIVEN a scenario for supported audiences in data"""
    def test_supported_audiences_in_data(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises supported audiences in data"""
        html = reporter.render(sample_data)
        m = re.search(r"var D = (.+);", html)
        """THEN the expected behavior for supported audiences in data is observed"""
        assert m is not None
        data = json.loads(m.group(1))
        assert "supported_audiences" in data
        assert "technical" in data["supported_audiences"]
        assert "executive" in data["supported_audiences"]

    """GIVEN a scenario for supported formats in data"""
    def test_supported_formats_in_data(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises supported formats in data"""
        html = reporter.render(sample_data)
        m = re.search(r"var D = (.+);", html)
        """THEN the expected behavior for supported formats in data is observed"""
        assert m is not None
        data = json.loads(m.group(1))
        assert "supported_formats" in data
        assert "markdown" in data["supported_formats"]
        assert "pdf" in data["supported_formats"]

    """GIVEN Format list must be audience-dependent matching CLI guide"""
    def test_audience_dependent_formats(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises audience dependent formats"""
        html = reporter.render(sample_data)
        # Standard audiences: markdown, plaintext, json only
        """THEN the expected behavior for audience dependent formats is observed"""
        assert "isExec=(aud==='executive')" in html
        assert "isNarr=(aud==='narrative'||aud==='customer-narrative')" in html
        # Executive: pdf, docx, markdown, json
        assert "['pdf','docx','markdown','json']" in html
        # Narrative: all 5
        assert "['pdf','docx','markdown','plaintext','json']" in html
        # Standard: 3 text formats
        assert "['markdown','plaintext','json']" in html

    """GIVEN Source Context must show the repo name prominently"""
    def test_wizard_source_shows_repo_name(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises wizard source shows repo name"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for wizard source shows repo name is observed"""
        assert "displayName" in html
        assert "ui.wizard.analysis_period" in html
        assert "ui.wizard.days_covered" in html

    """GIVEN Header must use LocaleSync qs-trigger-wrap pattern"""
    def test_header_matches_localesync_pattern(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises header matches localesync pattern"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for header matches localesync pattern is observed"""
        assert 'class="qs-trigger-wrap"' in html or "qs-trigger-wrap" in html
        assert 'class="qs-trigger"' in html
        assert 'class="header-logo"' in html
        assert 'class="header-subtitle"' in html
        assert "d-none" in html  # repo badge starts hidden

    """GIVEN Overview tab must be completely removed"""
    def test_no_overview_tab(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises no overview tab"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for no overview tab is observed"""
        assert 'data-tab="overview"' not in html
        assert "panel-overview" not in html
        assert "overview-content" not in html
        assert "renderOverview" not in html
