"""Tests for the narrative generation pipeline.

Covers the key behaviors of the fact-grounded narrative system:
- Fact extraction from ReleaseNotes
- Narrative composition (both modes)
- Claim validation / truthfulness guarantees
- Markdown and plaintext rendering
- CLI integration (generate, export)
- Isolation from the standard bullet-based pipeline
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import ChangeGroup, ReleaseNotes, ReleaseRange
from tests.conftest import make_change_item as _make_item


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


@pytest.fixture()
def sample_range() -> ReleaseRange:
    return ReleaseRange(
        from_ref="v2.0.0",
        to_ref="v2.1.0",
        version="2.1.0",
        title="Release 2.1.0",
        app_name="TestApp",
        release_date=date(2025, 6, 15),
    )


@pytest.fixture()
def rich_notes(sample_range: ReleaseRange) -> ReleaseNotes:
    """ReleaseNotes with a realistic mix of categories."""
    features = [
        _make_item(
            "feat: add OAuth2 authentication",
            description="Full OAuth2 flow with PKCE",
            scope="auth",
        ),
        _make_item("feat: add dark mode support", scope="ui"),
        _make_item("feat: implement search API", scope="api"),
    ]
    bugfixes = [
        _make_item("fix: pagination off-by-one error", ChangeCategory.BUGFIX, scope="api"),
        _make_item("fix: session token refresh", ChangeCategory.BUGFIX, scope="auth"),
    ]
    security = [
        _make_item(
            "fix: patch XSS vulnerability",
            ChangeCategory.SECURITY,
            importance=Importance.HIGH,
            scope="web",
        ),
    ]
    perf = [
        _make_item(
            "perf: optimize dashboard queries", ChangeCategory.PERFORMANCE, scope="dashboard"
        ),
    ]
    improvements = [
        _make_item("Improve error messages", ChangeCategory.IMPROVEMENT, scope="core"),
    ]
    breaking = [
        _make_item(
            "feat(api)!: Remove legacy API endpoints",
            ChangeCategory.BREAKING,
            breaking=True,
            scope="api",
            description="The v1 endpoints have been removed",
        ),
    ]
    infra = [_make_item("ci: Update CI pipeline", ChangeCategory.INFRASTRUCTURE)]
    refactor = [
        _make_item("refactor(db): Refactor database layer", ChangeCategory.REFACTOR, scope="db")
    ]

    all_items = features + bugfixes + security + perf + improvements + breaking + infra + refactor
    groups = []
    for cat_items, cat in [
        (breaking, ChangeCategory.BREAKING),
        (security, ChangeCategory.SECURITY),
        (features, ChangeCategory.FEATURE),
        (improvements, ChangeCategory.IMPROVEMENT),
        (bugfixes, ChangeCategory.BUGFIX),
        (perf, ChangeCategory.PERFORMANCE),
        (infra, ChangeCategory.INFRASTRUCTURE),
        (refactor, ChangeCategory.REFACTOR),
    ]:
        if cat_items:
            groups.append(ChangeGroup(category=cat, items=tuple(cat_items)))

    return ReleaseNotes(
        release_range=sample_range,
        groups=tuple(groups),
        highlights=tuple(security + breaking),
        breaking_changes=tuple(breaking),
        total_changes=len(all_items),
    )


@pytest.fixture()
def empty_notes(sample_range: ReleaseRange) -> ReleaseNotes:
    return ReleaseNotes(release_range=sample_range, groups=(), total_changes=0)


# ── Audience Views ───────────────────────────────────────────────────────────


class TestNarrativeCLI:
    """Verifies that narrative audiences work through the CLI."""

    """GIVEN a scenario for narrative audience in choices"""

    def test_narrative_audience_in_choices(self):
        """WHEN the test exercises narrative audience in choices"""
        from releasepilot.cli.app import _ALL_AUDIENCES

        """THEN the expected behavior for narrative audience in choices is observed"""
        assert "narrative" in _ALL_AUDIENCES
        assert "customer-narrative" in _ALL_AUDIENCES

    """GIVEN the guided workflow"""

    def test_narrative_format_choices_include_pdf_docx(self):
        """WHEN the test exercises narrative format choices include pdf docx"""
        from releasepilot.cli.guide import _FORMAT_CHOICES_NARRATIVE

        formats = [f[1] for f in _FORMAT_CHOICES_NARRATIVE]
        """THEN narrative format choices include PDF and DOCX"""
        assert "pdf" in formats
        assert "docx" in formats
        assert "markdown" in formats

    """GIVEN a structured source file"""

    def test_generate_narrative_markdown(self, tmp_path):
        """WHEN running generate --audience narrative"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(
            json.dumps(
                {
                    "changes": [
                        {"title": "Add user search", "category": "feature", "scope": "search"},
                        {"title": "Fix login bug", "category": "bugfix", "scope": "auth"},
                    ]
                }
            )
        )
        result = CliRunner().invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(source),
                "--audience",
                "narrative",
                "--from",
                "v1.0.0",
            ],
        )
        """THEN prose output"""
        assert result.exit_code == 0, result.output
        assert "Release Summary" in result.output or "Overview" in result.output

    """GIVEN source file"""

    def test_generate_customer_narrative(self, tmp_path):
        """WHEN running generate --audience customer-narrative"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(
            json.dumps(
                {
                    "changes": [
                        {"title": "Add dark mode", "category": "feature"},
                        {"title": "Improve loading speed", "category": "performance"},
                    ]
                }
            )
        )
        result = CliRunner().invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(source),
                "--audience",
                "customer-narrative",
                "--from",
                "v1.0.0",
            ],
        )
        """THEN customer prose"""
        assert result.exit_code == 0, result.output
        assert "Product Update" in result.output or "What's Changed" in result.output

    """GIVEN source file"""

    def test_generate_narrative_json(self, tmp_path):
        """WHEN running generate --audience narrative --format json"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(
            json.dumps({"changes": [{"title": "Add export feature", "category": "feature"}]})
        )
        result = CliRunner().invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(source),
                "--audience",
                "narrative",
                "--format",
                "json",
                "--from",
                "v1.0.0",
            ],
        )
        """THEN valid JSON"""
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["type"] == "narrative_brief"

    """GIVEN source file"""

    def test_export_narrative(self, tmp_path):
        """WHEN running export --audience narrative"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(
            json.dumps({"changes": [{"title": "Add billing module", "category": "feature"}]})
        )
        output = tmp_path / "narrative.md"
        result = CliRunner().invoke(
            cli,
            [
                "export",
                "--source-file",
                str(source),
                "--audience",
                "narrative",
                "-o",
                str(output),
                "--from",
                "v1.0.0",
            ],
        )
        """THEN file written"""
        assert result.exit_code == 0, result.output
        assert "Release Summary" in output.read_text() or "Overview" in output.read_text()

    """GIVEN source file"""

    @pytest.mark.skipif(not _pdf_available(), reason="reportlab not installed")
    def test_generate_narrative_pdf(self, tmp_path):
        """WHEN running generate --audience narrative --format pdf"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({"changes": [{"title": "Add search", "category": "feature"}]}))
        result = CliRunner().invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(source),
                "--audience",
                "narrative",
                "--format",
                "pdf",
                "--from",
                "v1.0.0",
            ],
        )
        """THEN PDF written"""
        assert result.exit_code == 0, result.output
        assert "Written to" in result.output

    """GIVEN source file"""

    @pytest.mark.skipif(not _docx_available(), reason="python-docx not installed")
    def test_generate_narrative_docx(self, tmp_path):
        """WHEN running generate --audience narrative --format docx"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(
            json.dumps({"changes": [{"title": "Add dashboard", "category": "feature"}]})
        )
        result = CliRunner().invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(source),
                "--audience",
                "narrative",
                "--format",
                "docx",
                "--from",
                "v1.0.0",
            ],
        )
        """THEN DOCX written"""
        assert result.exit_code == 0, result.output
        assert "Written to" in result.output

    """GIVEN source file"""

    @pytest.mark.skipif(not _pdf_available(), reason="reportlab not installed")
    def test_export_narrative_pdf(self, tmp_path):
        """WHEN running export --audience narrative --format pdf"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(
            json.dumps({"changes": [{"title": "Add notifications", "category": "feature"}]})
        )
        output = tmp_path / "narrative.pdf"
        result = CliRunner().invoke(
            cli,
            [
                "export",
                "--source-file",
                str(source),
                "--audience",
                "narrative",
                "--format",
                "pdf",
                "-o",
                str(output),
                "--from",
                "v1.0.0",
            ],
        )
        """THEN PDF file written"""
        assert result.exit_code == 0, result.output
        data = output.read_bytes()
        assert data[:5] == b"%PDF-"

    """GIVEN source file"""

    @pytest.mark.skipif(not _docx_available(), reason="python-docx not installed")
    def test_export_customer_narrative_docx(self, tmp_path):
        """WHEN exporting customer-narrative as DOCX"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(
            json.dumps(
                {"changes": [{"title": "Improve onboarding flow", "category": "improvement"}]}
            )
        )
        output = tmp_path / "update.docx"
        result = CliRunner().invoke(
            cli,
            [
                "export",
                "--source-file",
                str(source),
                "--audience",
                "customer-narrative",
                "--format",
                "docx",
                "-o",
                str(output),
                "--from",
                "v1.0.0",
            ],
        )
        """THEN valid DOCX"""
        assert result.exit_code == 0, result.output
        data = output.read_bytes()
        assert data[:2] == b"PK"
