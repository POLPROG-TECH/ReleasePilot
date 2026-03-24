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


class TestDashboardSchema:
    """Core data model correctness."""

    def test_empty_data_is_empty(self, empty_data: DashboardData) -> None:
        assert empty_data.is_empty is True

    def test_populated_data_not_empty(self, sample_data: DashboardData) -> None:
        assert sample_data.is_empty is False

    def test_computed_properties(self, sample_data: DashboardData) -> None:
        assert sample_data.total_breaking == 1
        assert sample_data.total_highlights == 1
        assert sample_data.categories_used == 5
        assert sample_data.total_authors == 5  # alice, bob, charlie, dave, eve

    def test_scopes_used(self, sample_data: DashboardData) -> None:
        scopes = sample_data.scopes_used
        assert "auth" in scopes
        assert "api" in scopes
        assert "core" in scopes
        assert "" not in scopes  # empty scope excluded

    def test_pipeline_stats_computed(self) -> None:
        stage = PipelineStageStats("filtered", 10, 7)
        assert stage.removed_count == 3
        assert stage.retention_percent == 70.0

    def test_pipeline_stats_zero_input(self) -> None:
        stage = PipelineStageStats("empty", 0, 0)
        assert stage.removed_count == 0
        assert stage.retention_percent == 100.0

    def test_default_dashboard_data(self) -> None:
        data = DashboardData()
        assert data.is_empty is True
        assert data.total_changes == 0
        assert data.total_breaking == 0
        assert data.total_authors == 0


# ── Reporter Tests ────────────────────────────────────────────────────────


class TestHtmlReporter:
    """HTML rendering correctness."""

    def test_render_produces_html(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_render_contains_data(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert '"total_changes":5' in html
        assert '"version":"1.1.0"' in html

    def test_render_replaces_placeholders(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "__DASHBOARD_DATA_JSON__" not in html
        assert "__GENERATED_AT__" not in html
        assert "__APP_VERSION__" not in html
        assert "__REPO_PATH__" not in html
        assert "__GENERATED_YEAR__" not in html

    def test_render_repo_path_in_json(self, reporter: HtmlReporter) -> None:
        data = DashboardData(repo_path="/home/user/my-project", generated_at="now")
        html = reporter.render(data)
        assert "my-project" in html

    def test_header_has_repo_badge(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert 'id="header-repo"' in html
        assert "header-repo-badge" in html

    def test_render_empty_data(self, reporter: HtmlReporter, empty_data: DashboardData) -> None:
        html = reporter.render(empty_data)
        assert '"is_empty":true' in html
        assert "No git tags found" in html

    def test_json_is_valid(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        m = re.search(r"var D = (.+);", html)
        assert m is not None, "Could not find data JSON in template"
        data = json.loads(m.group(1))
        assert data["total_changes"] == 5
        assert data["is_empty"] is False


# ── Template Structure Tests ──────────────────────────────────────────────


class TestTemplateStructure:
    """Verify the HTML template has the correct structure."""

    def test_has_theme_support(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert 'data-theme="light"' in html
        assert '[data-theme="dark"]' in html
        assert '[data-theme="midnight"]' in html

    def test_has_tabs(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert 'data-tab="generate"' in html
        assert 'data-tab="changes"' in html
        assert 'data-tab="artifacts"' in html
        assert 'data-tab="guide"' in html
        # Overview tab was removed — generate is the default
        assert 'data-tab="overview"' not in html

    def test_has_settings_panel(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert 'id="qsPanel"' in html
        assert "applyTheme" in html
        assert "applyLocale" in html
        assert "applyDensity" in html
        # Settings trigger button must have onclick
        assert 'id="qsTrigger"' in html
        assert 'onclick="toggleQS()"' in html

    def test_has_i18n(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "data-i18n=" in html
        assert "I18N" in html
        assert '"ui.tab.generate"' in html
        assert '"ui.tab.changes"' in html

    def test_has_first_run(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "first-run-panel" in html
        assert "first-run-action" in html

    def test_has_accessibility(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert 'class="skip-link"' in html
        assert 'role="tablist"' in html
        assert 'role="tab"' in html
        assert 'role="tabpanel"' in html
        assert "aria-selected" in html
        # Tab buttons have SVG icons (LocaleSync pattern)
        assert "<svg" in html

    def test_has_modal(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "modalOverlay" in html
        assert "openModal" in html
        assert "closeModal" in html

    def test_has_responsive_styles(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "@media(max-width:768px)" in html
        assert "@media(max-width:480px)" in html

    def test_localstorage_safe(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        js = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
        assert "function _ls(" in js
        assert "function _ss(" in js
        # No raw localStorage.setItem outside the helper
        raw_count = js.count("localStorage.setItem")
        assert raw_count <= 1, f"Found {raw_count} raw localStorage.setItem calls"

    def test_clipboard_has_catch(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert ".catch(function" in html

    def test_has_reduced_motion(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "prefers-reduced-motion" in html

    def test_has_print_styles(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "@media print" in html

    def test_has_footer(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "POLPROG" in html
        assert "ReleasePilot" in html
        assert "app-footer-copyright" in html
        assert "app-footer-tools" in html
        assert "app-footer-author" in html
        assert "app-footer-brand" in html
        assert "polprog.pl" in html
        assert "All rights reserved" in html

    def test_has_escape_function(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "function esc(" in html


# ── Wizard & Guide Tests ─────────────────────────────────────────────────


class TestWizardAndGuide:
    """Verify the wizard, guide, export, and preview UI elements exist."""

    def test_has_wizard_panel(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert 'id="panel-generate"' in html
        assert "wizard-steps" in html
        assert "wizard-panel" in html

    def test_has_wizard_steps(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        # All 6 steps
        for i in range(6):
            assert f'id="wiz-panel-{i}"' in html

    def test_has_wizard_audience_selection(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "wiz-audience-options" in html
        assert "AUDIENCE_INFO" in html
        assert "wizSelectAudience" in html

    def test_has_wizard_format_selection(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "wiz-format-options" in html
        assert "FORMAT_INFO" in html
        assert "wizSelectFormat" in html

    def test_has_wizard_preview(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "wiz-preview-area" in html
        assert "wizCopyPreview" in html
        assert "wizard-preview-area" in html

    def test_has_wizard_export(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "wiz-export-audience" in html
        assert "wiz-export-format" in html
        assert "wiz-export-filename" in html
        assert "wizDoExport" in html

    def test_has_wizard_navigation(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "wizard-footer" in html
        assert "wiz-prev-btn" in html
        assert "wiz-next-btn" in html
        assert "wizPrev" in html
        assert "wizNext" in html

    def test_has_wizard_generate_step(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "wiz-progress" in html
        assert "wizard-progress-spinner" in html
        assert "wiz-generate-result" in html

    def test_has_guide_panel(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert 'id="panel-guide"' in html
        assert "guide-content" in html
        assert "renderGuide" in html

    def test_has_guide_sections(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "guide-hero" in html
        assert "guide-pipeline" in html
        assert "guide-cards" in html
        assert "guide-cli-ref" in html

    def test_has_export_modal(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert "exportModalOverlay" in html
        assert "export-audience" in html
        assert "export-format" in html
        assert "export-filename" in html
        assert "openExportModal" in html
        assert "doExportFromModal" in html

    def test_has_artifact_filtering(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "artifact-aud-filter" in html
        assert "artifact-fmt-filter" in html
        assert "audienceFilter" in html

    def test_has_launch_wizard_action(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "launchWizard" in html

    def test_first_run_no_cli_commands(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """First-run panel should not show raw CLI commands as primary UX."""
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

    def test_has_find_artifact_function(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        assert "function findArtifact(" in html

    def test_wizard_i18n_keys(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert '"ui.tab.generate"' in html
        assert '"ui.tab.guide"' in html
        assert '"ui.wizard.source"' in html
        assert '"ui.wizard.audience"' in html
        assert '"ui.wizard.format"' in html
        assert '"ui.wizard.preview"' in html
        assert '"ui.wizard.export_step"' in html
        assert '"ui.guide.hero_title"' in html

    def test_wizard_i18n_polish(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        html = reporter.render(sample_data)
        assert '"ui.tab.generate":"Generuj"' in html or '"ui.tab.generate": "Generuj"' in html
        assert '"ui.tab.guide":"Przewodnik"' in html or '"ui.tab.guide": "Przewodnik"' in html

    def test_supported_audiences_in_data(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        m = re.search(r"var D = (.+);", html)
        assert m is not None
        data = json.loads(m.group(1))
        assert "supported_audiences" in data
        assert "technical" in data["supported_audiences"]
        assert "executive" in data["supported_audiences"]

    def test_supported_formats_in_data(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        html = reporter.render(sample_data)
        m = re.search(r"var D = (.+);", html)
        assert m is not None
        data = json.loads(m.group(1))
        assert "supported_formats" in data
        assert "markdown" in data["supported_formats"]
        assert "pdf" in data["supported_formats"]

    def test_audience_dependent_formats(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """Format list must be audience-dependent matching CLI guide."""
        html = reporter.render(sample_data)
        # Standard audiences: markdown, plaintext, json only
        assert "isExec=(aud==='executive')" in html
        assert "isNarr=(aud==='narrative'||aud==='customer-narrative')" in html
        # Executive: pdf, docx, markdown, json
        assert "['pdf','docx','markdown','json']" in html
        # Narrative: all 5
        assert "['pdf','docx','markdown','plaintext','json']" in html
        # Standard: 3 text formats
        assert "['markdown','plaintext','json']" in html

    def test_wizard_source_shows_repo_name(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """Source Context must show the repo name prominently."""
        html = reporter.render(sample_data)
        assert "displayName" in html
        assert "ui.wizard.analysis_period" in html
        assert "ui.wizard.days_covered" in html

    def test_header_matches_localesync_pattern(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """Header must use LocaleSync qs-trigger-wrap pattern."""
        html = reporter.render(sample_data)
        assert 'class="qs-trigger-wrap"' in html or "qs-trigger-wrap" in html
        assert 'class="qs-trigger"' in html
        assert 'class="header-logo"' in html
        assert 'class="header-subtitle"' in html
        assert "d-none" in html  # repo badge starts hidden

    def test_no_overview_tab(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """Overview tab must be completely removed."""
        html = reporter.render(sample_data)
        assert 'data-tab="overview"' not in html
        assert "panel-overview" not in html
        assert "overview-content" not in html
        assert "renderOverview" not in html


# ── Use Case Tests ────────────────────────────────────────────────────────


class TestDashboardUseCase:
    """Use case handles errors gracefully."""

    def test_error_returns_diagnostics(self) -> None:
        from releasepilot.config.settings import Settings
        from releasepilot.dashboard.use_case import DashboardUseCase

        # Build settings pointing to a non-existent repo
        settings = Settings(repo_path="/nonexistent/repo/path")
        uc = DashboardUseCase()
        data = uc.execute(settings)
        assert data.is_empty is True
        assert len(data.diagnostics) > 0
