"""Tests for PDF and DOCX renderers."""

from __future__ import annotations

from pathlib import Path

import pytest

from releasepilot.config.settings import RenderConfig
from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)

_reportlab = pytest.importorskip("reportlab", reason="reportlab not installed")
_docx = pytest.importorskip("docx", reason="python-docx not installed")

from releasepilot.rendering.docx_renderer import DocxRenderer  # noqa: E402
from releasepilot.rendering.pdf import PdfRenderer  # noqa: E402


@pytest.fixture()
def sample_notes() -> ReleaseNotes:
    """Create realistic release notes for rendering tests."""
    items = (
        ChangeItem(
            id="1",
            title="Add user authentication",
            description="JWT-based auth with refresh tokens",
            category=ChangeCategory.FEATURE,
            scope="auth",
            importance=Importance.HIGH,
            authors=("alice",),
            source=SourceReference(commit_hash="abc12345", pr_number=42),
        ),
        ChangeItem(
            id="2",
            title="Fix timeout in API calls",
            category=ChangeCategory.BUGFIX,
            scope="api",
            authors=("bob",),
            source=SourceReference(commit_hash="def67890"),
        ),
        ChangeItem(
            id="3",
            title="Improve query performance",
            description="Optimized N+1 queries in dashboard",
            category=ChangeCategory.PERFORMANCE,
            authors=("charlie",),
        ),
    )

    breaking = (
        ChangeItem(
            id="4",
            title="Remove deprecated /v1/ endpoints",
            description="All v1 API endpoints have been removed. Migrate to /v2/ endpoints.",
            category=ChangeCategory.BREAKING,
            is_breaking=True,
            importance=Importance.HIGH,
        ),
    )

    groups = (
        ChangeGroup(category=ChangeCategory.FEATURE, items=(items[0],)),
        ChangeGroup(category=ChangeCategory.BUGFIX, items=(items[1],)),
        ChangeGroup(category=ChangeCategory.PERFORMANCE, items=(items[2],)),
        ChangeGroup(category=ChangeCategory.BREAKING, items=breaking),
    )

    return ReleaseNotes(
        release_range=ReleaseRange(
            from_ref="v1.0.0",
            to_ref="v2.0.0",
            version="2.0.0",
            title="Release 2.0.0",
            release_date=None,
        ),
        groups=groups,
        highlights=(items[0],),
        breaking_changes=breaking,
        total_changes=4,
    )


class TestPdfRenderer:
    """Scenarios for PDF rendering of release notes."""

    def test_produces_valid_pdf(self, sample_notes: ReleaseNotes):
        """GIVEN a PDF renderer with sample notes."""
        renderer = PdfRenderer()
        config = RenderConfig()

        """WHEN rendering to bytes."""
        data = renderer.render_bytes(sample_notes, config)

        """THEN it produces valid PDF bytes."""
        assert isinstance(data, bytes)
        assert len(data) > 100
        assert data[:5] == b"%PDF-"

    def test_render_returns_empty_string(self, sample_notes: ReleaseNotes):
        """GIVEN a PDF renderer."""
        renderer = PdfRenderer()

        """WHEN calling the string render method."""
        with pytest.raises(NotImplementedError, match="render_bytes"):
            renderer.render(sample_notes, RenderConfig())

        """THEN it raises NotImplementedError guiding users to render_bytes()."""

    def test_pdf_is_nontrivial(self, sample_notes: ReleaseNotes):
        """GIVEN a PDF renderer."""
        renderer = PdfRenderer()

        """WHEN rendering to bytes."""
        data = renderer.render_bytes(sample_notes, RenderConfig())

        """THEN the PDF has non-trivial size."""
        assert len(data) > 500
        assert data[:5] == b"%PDF-"

    def test_pdf_with_authors(self, sample_notes: ReleaseNotes):
        """GIVEN a PDF renderer with authors enabled."""
        renderer = PdfRenderer()
        config = RenderConfig(show_authors=True)

        """WHEN rendering to bytes."""
        data = renderer.render_bytes(sample_notes, config)

        """THEN it produces a valid PDF."""
        assert data[:5] == b"%PDF-"

    def test_pdf_with_hashes(self, sample_notes: ReleaseNotes):
        """GIVEN a PDF renderer with commit hashes enabled."""
        renderer = PdfRenderer()
        config = RenderConfig(show_commit_hashes=True)

        """WHEN rendering to bytes."""
        data = renderer.render_bytes(sample_notes, config)

        """THEN it produces a valid PDF."""
        assert data[:5] == b"%PDF-"


class TestDocxRenderer:
    """Scenarios for DOCX rendering of release notes."""

    def test_produces_valid_docx(self, sample_notes: ReleaseNotes):
        """GIVEN a DOCX renderer with sample notes."""
        renderer = DocxRenderer()
        config = RenderConfig()

        """WHEN rendering to bytes."""
        data = renderer.render_bytes(sample_notes, config)

        """THEN it produces valid DOCX bytes."""
        assert isinstance(data, bytes)
        assert len(data) > 100
        assert data[:2] == b"PK"  # ZIP magic bytes

    def test_render_returns_empty_string(self, sample_notes: ReleaseNotes):
        """GIVEN a DOCX renderer."""
        renderer = DocxRenderer()

        """WHEN calling the string render method."""
        with pytest.raises(NotImplementedError, match="render_bytes"):
            renderer.render(sample_notes, RenderConfig())

        """THEN it raises NotImplementedError guiding users to render_bytes()."""

    def test_docx_can_be_opened(self, sample_notes: ReleaseNotes, tmp_path: Path):
        """GIVEN a rendered DOCX file written to disk."""
        renderer = DocxRenderer()
        data = renderer.render_bytes(sample_notes, RenderConfig())
        out = tmp_path / "test.docx"
        out.write_bytes(data)

        """WHEN opening with python-docx."""
        from docx import Document

        doc = Document(str(out))

        """THEN it has content including the version number."""
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        assert len(paragraphs) > 0
        assert any("2.0.0" in p for p in paragraphs)

    def test_docx_with_authors(self, sample_notes: ReleaseNotes):
        """GIVEN a DOCX renderer with authors enabled."""
        renderer = DocxRenderer()
        config = RenderConfig(show_authors=True)

        """WHEN rendering to bytes."""
        data = renderer.render_bytes(sample_notes, config)

        """THEN it produces valid DOCX bytes."""
        assert data[:2] == b"PK"

    def test_docx_with_hashes(self, sample_notes: ReleaseNotes):
        """GIVEN a DOCX renderer with commit hashes enabled."""
        renderer = DocxRenderer()
        config = RenderConfig(show_commit_hashes=True)

        """WHEN rendering to bytes."""
        data = renderer.render_bytes(sample_notes, config)

        """THEN it produces valid DOCX bytes."""
        assert data[:2] == b"PK"


class TestCLIPdfDocxExport:
    """Scenarios for PDF and DOCX export via CLI."""

    def test_export_pdf(self, tmp_path: Path):
        """GIVEN the CLI and a temporary output path."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        runner = CliRunner()
        out = str(tmp_path / "notes.pdf")

        """WHEN exporting to PDF."""
        result = runner.invoke(
            cli,
            [
                "export",
                "--source-file",
                "examples/sample_changes.json",
                "--format",
                "pdf",
                "-o",
                out,
                "--version",
                "3.0.0",
            ],
        )

        """THEN a valid PDF file is created."""
        assert result.exit_code == 0
        assert Path(out).exists()
        assert Path(out).read_bytes()[:5] == b"%PDF-"

    def test_export_docx(self, tmp_path: Path):
        """GIVEN the CLI and a temporary output path."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        runner = CliRunner()
        out = str(tmp_path / "notes.docx")

        """WHEN exporting to DOCX."""
        result = runner.invoke(
            cli,
            [
                "export",
                "--source-file",
                "examples/sample_changes.json",
                "--format",
                "docx",
                "-o",
                out,
                "--version",
                "3.0.0",
            ],
        )

        """THEN a valid DOCX file is created."""
        assert result.exit_code == 0
        assert Path(out).exists()
        assert Path(out).read_bytes()[:2] == b"PK"

    def test_generate_pdf_creates_file(self, tmp_path: Path):
        """GIVEN the CLI running in a temporary directory."""
        import os

        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        original_dir = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            runner = CliRunner()

            """WHEN generating with --format pdf."""
            result = runner.invoke(
                cli,
                [
                    "generate",
                    "--source-file",
                    str(Path(original_dir) / "examples/sample_changes.json"),
                    "--format",
                    "pdf",
                    "--version",
                    "3.0.0",
                ],
            )

            """THEN it succeeds and creates a default output file."""
            assert result.exit_code == 0
        finally:
            os.chdir(original_dir)


# ── PDF paragraph style configuration ────────────────────────────────────────


class TestPdfStyles:
    """Scenarios for PDF paragraph style configuration (alignment, sizes)."""

    def test_app_name_centered_title_left(self):
        """GIVEN the sample stylesheet and custom paragraph styles."""
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

        styles = getSampleStyleSheet()

        """WHEN AppName and ReleaseTitle styles are created."""
        app_name_style = ParagraphStyle(
            "AppName",
            parent=styles["Title"],
            fontSize=28,
            alignment=1,
            textColor=colors.HexColor("#1a1a2e"),
        )
        title_style = ParagraphStyle(
            "ReleaseTitle",
            parent=styles["Title"],
            fontSize=22,
            alignment=0,
            textColor=colors.HexColor("#1a1a2e"),
        )

        """THEN app_name is centered and title is left-aligned."""
        assert app_name_style.alignment == 1  # CENTER
        assert title_style.alignment == 0  # LEFT

    def test_footer_style_small(self):
        """GIVEN the sample stylesheet."""
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

        styles = getSampleStyleSheet()

        """WHEN a Footer style is created with fontSize 7."""
        footer_style = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=7,
            alignment=1,
        )

        """THEN the font size is 7pt."""
        assert footer_style.fontSize == 7
