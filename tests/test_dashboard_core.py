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


class TestDashboardSchema:
    """Core data model correctness."""

    """GIVEN a scenario for empty data is empty"""

    def test_empty_data_is_empty(self, empty_data: DashboardData) -> None:
        """WHEN the test exercises empty data is empty"""
        """THEN the expected behavior for empty data is empty is observed"""
        assert empty_data.is_empty is True

    """GIVEN a scenario for populated data not empty"""

    def test_populated_data_not_empty(self, sample_data: DashboardData) -> None:
        """WHEN the test exercises populated data not empty"""
        """THEN the expected behavior for populated data not empty is observed"""
        assert sample_data.is_empty is False

    """GIVEN a scenario for computed properties"""

    def test_computed_properties(self, sample_data: DashboardData) -> None:
        """WHEN the test exercises computed properties"""
        """THEN the expected behavior for computed properties is observed"""
        assert sample_data.total_breaking == 1
        assert sample_data.total_highlights == 1
        assert sample_data.categories_used == 5
        assert sample_data.total_authors == 5  # alice, bob, charlie, dave, eve

    """GIVEN a scenario for scopes used"""

    def test_scopes_used(self, sample_data: DashboardData) -> None:
        """WHEN the test exercises scopes used"""
        scopes = sample_data.scopes_used
        """THEN the expected behavior for scopes used is observed"""
        assert "auth" in scopes
        assert "api" in scopes
        assert "core" in scopes
        assert "" not in scopes  # empty scope excluded

    """GIVEN a scenario for pipeline stats computed"""

    def test_pipeline_stats_computed(self) -> None:
        """WHEN the test exercises pipeline stats computed"""
        stage = PipelineStageStats("filtered", 10, 7)
        """THEN the expected behavior for pipeline stats computed is observed"""
        assert stage.removed_count == 3
        assert stage.retention_percent == 70.0

    """GIVEN a scenario for pipeline stats zero input"""

    def test_pipeline_stats_zero_input(self) -> None:
        """WHEN the test exercises pipeline stats zero input"""
        stage = PipelineStageStats("empty", 0, 0)
        """THEN the expected behavior for pipeline stats zero input is observed"""
        assert stage.removed_count == 0
        assert stage.retention_percent == 100.0

    """GIVEN a scenario for default dashboard data"""

    def test_default_dashboard_data(self) -> None:
        """WHEN the test exercises default dashboard data"""
        data = DashboardData()
        """THEN the expected behavior for default dashboard data is observed"""
        assert data.is_empty is True
        assert data.total_changes == 0
        assert data.total_breaking == 0
        assert data.total_authors == 0


class TestHtmlReporter:
    """HTML rendering correctness."""

    """GIVEN a scenario for render produces html"""

    def test_render_produces_html(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises render produces html"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for render produces html is observed"""
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    """GIVEN a scenario for render contains data"""

    def test_render_contains_data(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises render contains data"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for render contains data is observed"""
        assert '"total_changes":5' in html
        assert '"version":"1.1.0"' in html

    """GIVEN a scenario for render replaces placeholders"""

    def test_render_replaces_placeholders(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises render replaces placeholders"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for render replaces placeholders is observed"""
        assert "__DASHBOARD_DATA_JSON__" not in html
        assert "__GENERATED_AT__" not in html
        assert "__APP_VERSION__" not in html
        assert "__REPO_PATH__" not in html
        assert "__GENERATED_YEAR__" not in html

    """GIVEN a scenario for render repo path in json"""

    def test_render_repo_path_in_json(self, reporter: HtmlReporter) -> None:
        """WHEN the test exercises render repo path in json"""
        data = DashboardData(repo_path="/home/user/my-project", generated_at="now")
        html = reporter.render(data)
        """THEN the expected behavior for render repo path in json is observed"""
        assert "my-project" in html

    """GIVEN a scenario for header has repo badge"""

    def test_header_has_repo_badge(
        self, reporter: HtmlReporter, sample_data: DashboardData
    ) -> None:
        """WHEN the test exercises header has repo badge"""
        html = reporter.render(sample_data)
        """THEN the expected behavior for header has repo badge is observed"""
        assert 'id="header-repo"' in html
        assert "header-repo-badge" in html

    """GIVEN a scenario for render empty data"""

    def test_render_empty_data(self, reporter: HtmlReporter, empty_data: DashboardData) -> None:
        """WHEN the test exercises render empty data"""
        html = reporter.render(empty_data)
        """THEN the expected behavior for render empty data is observed"""
        assert '"is_empty":true' in html
        assert "No git tags found" in html

    """GIVEN a scenario for json is valid"""

    def test_json_is_valid(self, reporter: HtmlReporter, sample_data: DashboardData) -> None:
        """WHEN the test exercises json is valid"""
        html = reporter.render(sample_data)
        m = re.search(r"var D = (.+);", html)
        """THEN the expected behavior for json is valid is observed"""
        assert m is not None, "Could not find data JSON in template"
        data = json.loads(m.group(1))
        assert data["total_changes"] == 5
        assert data["is_empty"] is False


class TestDashboardUseCase:
    """Use case handles errors gracefully."""

    """GIVEN a scenario for error returns diagnostics"""

    def test_error_returns_diagnostics(self) -> None:
        """WHEN the test exercises error returns diagnostics"""
        from releasepilot.config.settings import Settings
        from releasepilot.dashboard.use_case import DashboardUseCase

        # Build settings pointing to a non-existent repo
        settings = Settings(repo_path="/nonexistent/repo/path")
        uc = DashboardUseCase()
        data = uc.execute(settings)
        """THEN the expected behavior for error returns diagnostics is observed"""
        assert data.is_empty is True
        assert len(data.diagnostics) > 0
