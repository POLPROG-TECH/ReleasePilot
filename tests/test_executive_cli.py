"""Tests for executive brief composition and rendering.

Covers:
- ExecutiveBrief model and composition logic
- Business-language title transformation
- Executive summary generation
- Impact area grouping
- Risk extraction and next-steps generation
- Executive Markdown, PDF, and DOCX renderers
- CLI integration for executive audience
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from click.testing import CliRunner

from releasepilot.audience.executive import (
    ExecutiveBrief,
    compose_executive_brief,
)
from releasepilot.cli.app import cli
from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)


def _pdf_available() -> bool:
    try:
        import reportlab  # noqa: F401

        return True
    except ImportError:
        return False


def _docx_available() -> bool:
    try:
        import docx  # noqa: F401

        return True
    except ImportError:
        return False


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_item(
    title: str,
    category: ChangeCategory = ChangeCategory.FEATURE,
    *,
    breaking: bool = False,
    importance: Importance = Importance.NORMAL,
    description: str = "",
    scope: str = "",
) -> ChangeItem:
    return ChangeItem(
        id=f"id-{title[:10]}",
        title=title,
        description=description,
        category=category,
        scope=scope,
        importance=importance,
        is_breaking=breaking,
        source=SourceReference(commit_hash="abc12345"),
        authors=("alice",),
    )


@pytest.fixture()
def sample_notes() -> ReleaseNotes:
    """ReleaseNotes with a realistic mix of changes."""
    items_by_cat = {
        ChangeCategory.FEATURE: [
            _make_item("feat: add OAuth2 authentication", description="Full OAuth2 flow with PKCE"),
            _make_item("feat: add dark mode support"),
            _make_item("feat: implement search API"),
        ],
        ChangeCategory.BUGFIX: [
            _make_item("fix: pagination off-by-one error", ChangeCategory.BUGFIX),
            _make_item("fix: session token refresh", ChangeCategory.BUGFIX),
        ],
        ChangeCategory.SECURITY: [
            _make_item(
                "fix: patch XSS vulnerability", ChangeCategory.SECURITY, importance=Importance.HIGH
            ),
        ],
        ChangeCategory.PERFORMANCE: [
            _make_item("perf: optimize dashboard queries", ChangeCategory.PERFORMANCE),
        ],
        ChangeCategory.IMPROVEMENT: [
            _make_item("improve error messages", ChangeCategory.IMPROVEMENT),
        ],
        ChangeCategory.BREAKING: [
            _make_item(
                "feat!: remove /api/v1 endpoints",
                ChangeCategory.BREAKING,
                breaking=True,
                description="All v1 API endpoints have been removed",
            ),
        ],
        ChangeCategory.DEPRECATION: [
            _make_item("deprecate legacy webhook format", ChangeCategory.DEPRECATION),
        ],
    }

    groups = tuple(
        ChangeGroup(category=cat, items=tuple(items)) for cat, items in items_by_cat.items()
    )

    all_items = [i for items in items_by_cat.values() for i in items]
    highlights = tuple(i for i in all_items if i.is_breaking or i.importance == Importance.HIGH)
    breaking = tuple(i for i in all_items if i.is_breaking)

    return ReleaseNotes(
        release_range=ReleaseRange(
            from_ref="v2.0.0",
            to_ref="v3.0.0",
            version="3.0.0",
            title="Release 3.0.0",
            release_date=date(2026, 3, 16),
        ),
        groups=groups,
        highlights=highlights,
        breaking_changes=breaking,
        total_changes=len(all_items),
    )


@pytest.fixture()
def sample_brief(sample_notes: ReleaseNotes) -> ExecutiveBrief:
    return compose_executive_brief(sample_notes)


class TestCliExecutiveAudience:
    """Scenarios for CLI integration with executive audience."""

    """GIVEN sample changes and executive audience"""

    def test_generate_executive_markdown(self):
        runner = CliRunner()

        """WHEN generating Markdown via CLI"""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                "examples/sample_changes.json",
                "--audience",
                "executive",
                "--version",
                "3.0.0",
            ],
        )

        """THEN output contains executive sections"""
        assert result.exit_code == 0
        assert "Executive Summary" in result.output
        assert "Key Achievements" in result.output

    """GIVEN sample changes and executive audience"""

    def test_generate_executive_json(self):
        runner = CliRunner()

        """WHEN generating JSON via CLI"""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                "examples/sample_changes.json",
                "--audience",
                "executive",
                "--format",
                "json",
                "--version",
                "3.0.0",
            ],
        )

        """THEN output is valid executive brief JSON"""
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["type"] == "executive_brief"

    """GIVEN sample changes and executive audience"""

    @pytest.mark.skipif(not _pdf_available(), reason="reportlab not installed")
    def test_export_executive_pdf(self, tmp_path):
        runner = CliRunner()
        out = str(tmp_path / "brief.pdf")

        """WHEN exporting PDF via CLI"""
        result = runner.invoke(
            cli,
            [
                "export",
                "--source-file",
                "examples/sample_changes.json",
                "--audience",
                "executive",
                "--format",
                "pdf",
                "--version",
                "3.0.0",
                "-o",
                out,
            ],
        )

        """THEN a valid PDF file is created"""
        assert result.exit_code == 0
        assert (tmp_path / "brief.pdf").exists()
        data = (tmp_path / "brief.pdf").read_bytes()
        assert data[:5] == b"%PDF-"

    """GIVEN sample changes and executive audience"""

    @pytest.mark.skipif(not _docx_available(), reason="python-docx not installed")
    def test_export_executive_docx(self, tmp_path):
        runner = CliRunner()
        out = str(tmp_path / "brief.docx")

        """WHEN exporting DOCX via CLI"""
        result = runner.invoke(
            cli,
            [
                "export",
                "--source-file",
                "examples/sample_changes.json",
                "--audience",
                "executive",
                "--format",
                "docx",
                "--version",
                "3.0.0",
                "-o",
                out,
            ],
        )

        """THEN a valid DOCX file is created"""
        assert result.exit_code == 0
        assert (tmp_path / "brief.docx").exists()
        data = (tmp_path / "brief.docx").read_bytes()
        assert data[:2] == b"PK"

    """GIVEN sample changes and executive audience"""

    def test_executive_no_raw_commit_prefixes(self):
        runner = CliRunner()

        """WHEN generating via CLI"""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                "examples/sample_changes.json",
                "--audience",
                "executive",
                "--version",
                "3.0.0",
            ],
        )

        """THEN no raw commit prefixes appear"""
        assert result.exit_code == 0
        # Should not contain raw conventional commit prefixes
        assert "feat:" not in result.output
        assert "fix:" not in result.output
