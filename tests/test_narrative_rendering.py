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

from releasepilot.audience.narrative import (
    compose_narrative,
)
from releasepilot.domain.enums import Audience, ChangeCategory, Importance
from releasepilot.domain.models import ChangeGroup, ReleaseNotes, ReleaseRange
from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer
from releasepilot.rendering.narrative_plain import NarrativePlaintextRenderer
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


# ── Fact Extraction ──────────────────────────────────────────────────────────


# ── Narrative Composition ────────────────────────────────────────────────────


# ── Claim Validation ─────────────────────────────────────────────────────────


# ── Rendering ────────────────────────────────────────────────────────────────


# ── NarrativeBrief Model ────────────────────────────────────────────────────


# ── Grounding Guarantees ─────────────────────────────────────────────────────


# ── CLI Integration ──────────────────────────────────────────────────────────


# ── Isolation / Non-Regression ───────────────────────────────────────────────


# ── Audience Views ───────────────────────────────────────────────────────────


class TestNarrativeRendering:
    """Verifies that renderers produce correct output formats."""

    """GIVEN a composed brief"""

    def test_markdown_contains_headings_and_prose(self, rich_notes: ReleaseNotes):
        """WHEN rendering markdown"""
        brief = compose_narrative(rich_notes)
        output = NarrativeMarkdownRenderer().render(brief)
        """THEN output has headings, app name, prose"""
        assert "# TestApp" in output
        assert "2.1.0" in output
        assert "## Overview" in output or "## What" in output
        assert "verified facts" in output.lower()

    """GIVEN a composed brief"""

    def test_markdown_has_no_bullet_lists_in_body(self, rich_notes: ReleaseNotes):
        """WHEN rendering"""
        brief = compose_narrative(rich_notes)
        output = NarrativeMarkdownRenderer().render(brief)
        body_lines = [
            line
            for line in output.split("\n")
            if line.strip()
            and not line.startswith("#")
            and not line.startswith("*")
            and not line.startswith("---")
            and not line.startswith("|")
        ]
        for line in body_lines:
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("• "):
                assert "ReleasePilot" in line or "verified" in line, (
                    f"Unexpected bullet point in narrative: {line}"
                )

    """GIVEN notes with breaking changes"""

    def test_markdown_breaking_section(self, rich_notes: ReleaseNotes):
        """WHEN rendering"""
        brief = compose_narrative(rich_notes)
        output = NarrativeMarkdownRenderer().render(brief)
        """THEN breaking section present"""
        assert "Important Changes" in output or "breaking" in output.lower()

    """GIVEN a composed brief"""

    def test_json_output_structure(self, rich_notes: ReleaseNotes):
        """WHEN rendering JSON"""
        brief = compose_narrative(rich_notes)
        parsed = json.loads(NarrativeMarkdownRenderer().render_json(brief))
        """THEN includes fact layer for auditability"""
        assert parsed["type"] == "narrative_brief"
        assert parsed["mode"] == "narrative"
        assert isinstance(parsed["fact_groups"], list)
        assert parsed["total_facts"] > 0

    """GIVEN customer_facing flag"""

    @pytest.mark.parametrize(
        "customer_facing,expected_mode",
        [
            (False, "narrative"),
            (True, "customer-narrative"),
        ],
    )
    def test_json_mode_matches_composition(self, rich_notes, customer_facing, expected_mode):
        """WHEN rendering JSON"""
        brief = compose_narrative(rich_notes, customer_facing=customer_facing)
        parsed = json.loads(NarrativeMarkdownRenderer().render_json(brief))
        """THEN mode field matches"""
        assert parsed["mode"] == expected_mode

    """GIVEN a composed brief"""

    def test_plaintext_rendering(self, rich_notes: ReleaseNotes):
        """WHEN rendering plaintext"""
        brief = compose_narrative(rich_notes)
        output = NarrativePlaintextRenderer().render(brief)
        """THEN produces readable terminal output"""
        assert "TestApp" in output
        assert "Release Summary" in output
        assert "changes from" in output.lower() or "source items" in output.lower()

    """GIVEN empty notes"""

    def test_empty_narrative_renders(self, empty_notes: ReleaseNotes):
        """WHEN rendering plaintext"""
        brief = compose_narrative(empty_notes)
        output = NarrativePlaintextRenderer().render(brief)
        """THEN graceful 'no changes' output"""
        assert "no notable changes" in output.lower()

    """GIVEN a composed brief"""

    @pytest.mark.skipif(not _pdf_available(), reason="reportlab not installed")
    def test_pdf_produces_valid_bytes(self, rich_notes: ReleaseNotes):
        """WHEN rendering PDF"""
        from releasepilot.rendering.narrative_pdf import NarrativePdfRenderer

        brief = compose_narrative(rich_notes)
        data = NarrativePdfRenderer().render_bytes(brief)
        """THEN valid PDF bytes produced"""
        assert data[:5] == b"%PDF-"
        assert len(data) > 1000

    """GIVEN a composed brief"""

    @pytest.mark.skipif(not _docx_available(), reason="python-docx not installed")
    def test_docx_produces_valid_bytes(self, rich_notes: ReleaseNotes):
        """WHEN rendering DOCX"""
        from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer

        brief = compose_narrative(rich_notes)
        data = NarrativeDocxRenderer().render_bytes(brief)
        """THEN valid DOCX (ZIP) bytes produced"""
        assert data[:2] == b"PK"
        assert len(data) > 1000

    """GIVEN either narrative mode"""

    @pytest.mark.skipif(not _pdf_available(), reason="reportlab not installed")
    @pytest.mark.parametrize("customer_facing", [False, True])
    def test_pdf_customer_mode(self, rich_notes: ReleaseNotes, customer_facing: bool):
        """WHEN rendering PDF"""
        from releasepilot.rendering.narrative_pdf import NarrativePdfRenderer

        brief = compose_narrative(rich_notes, customer_facing=customer_facing)
        data = NarrativePdfRenderer().render_bytes(brief)
        """THEN produces valid output"""
        assert data[:5] == b"%PDF-"

    """GIVEN either narrative mode"""

    @pytest.mark.skipif(not _docx_available(), reason="python-docx not installed")
    @pytest.mark.parametrize("customer_facing", [False, True])
    def test_docx_customer_mode(self, rich_notes: ReleaseNotes, customer_facing: bool):
        """WHEN rendering DOCX"""
        from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer

        brief = compose_narrative(rich_notes, customer_facing=customer_facing)
        data = NarrativeDocxRenderer().render_bytes(brief)
        """THEN produces valid output"""
        assert data[:2] == b"PK"


class TestNarrativeIsolation:
    """Verifies that the narrative pipeline does not affect the standard pipeline."""

    """GIVEN rich notes"""

    def test_standard_pipeline_still_produces_bullets(self, rich_notes: ReleaseNotes):
        """WHEN rendering with standard renderer"""
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.markdown import MarkdownRenderer

        output = MarkdownRenderer().render(rich_notes, RenderConfig())
        """THEN bullet output unchanged"""
        assert "- " in output

    """GIVEN rich notes"""

    def test_compose_does_not_mutate_input(self, rich_notes: ReleaseNotes):
        """WHEN composing narrative"""
        original_total = rich_notes.total_changes
        original_groups = len(rich_notes.groups)
        compose_narrative(rich_notes)
        """THEN input ReleaseNotes unchanged"""
        assert rich_notes.total_changes == original_total
        assert len(rich_notes.groups) == original_groups

    """GIVEN same notes"""

    def test_narrative_and_standard_produce_different_output(self, rich_notes: ReleaseNotes):
        """WHEN rendering both ways"""
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.markdown import MarkdownRenderer

        standard = MarkdownRenderer().render(rich_notes, RenderConfig())
        narrative = NarrativeMarkdownRenderer().render(compose_narrative(rich_notes))
        """THEN outputs are distinct"""
        assert standard != narrative
        assert standard.count("\n- ") > narrative.count("\n- ")


class TestNarrativeAudienceViews:
    """Verifies that narrative audience transforms work through apply_audience."""

    """GIVEN a scenario for narrative preserves all categories"""

    def test_narrative_preserves_all_categories(self, rich_notes: ReleaseNotes):
        """WHEN the test exercises narrative preserves all categories"""
        from releasepilot.audience.views import apply_audience

        result = apply_audience(rich_notes, Audience.NARRATIVE)
        """THEN the expected behavior for narrative preserves all categories is observed"""
        assert {g.category for g in result.groups} == {g.category for g in rich_notes.groups}

    """GIVEN a scenario for customer narrative hides internal"""

    def test_customer_narrative_hides_internal(self, rich_notes: ReleaseNotes):
        """WHEN the test exercises customer narrative hides internal"""
        from releasepilot.audience.views import apply_audience

        result = apply_audience(rich_notes, Audience.CUSTOMER_NARRATIVE)
        result_cats = {g.category for g in result.groups}
        """THEN the expected behavior for customer narrative hides internal is observed"""
        assert ChangeCategory.REFACTOR not in result_cats
        assert ChangeCategory.INFRASTRUCTURE not in result_cats
