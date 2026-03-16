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
    FactGroup,
    FactItem,
    NarrativeBrief,
    collect_all_source_ids,
    compose_narrative,
    extract_fact_groups,
    extract_facts,
    validate_narrative,
)
from releasepilot.domain.enums import Audience, ChangeCategory, Importance
from releasepilot.domain.models import ChangeGroup, ReleaseNotes, ReleaseRange
from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer
from releasepilot.rendering.narrative_plain import NarrativePlaintextRenderer
from tests.conftest import make_change_item as _make_item

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
        _make_item("feat: add OAuth2 authentication", description="Full OAuth2 flow with PKCE", scope="auth"),
        _make_item("feat: add dark mode support", scope="ui"),
        _make_item("feat: implement search API", scope="api"),
    ]
    bugfixes = [
        _make_item("fix: pagination off-by-one error", ChangeCategory.BUGFIX, scope="api"),
        _make_item("fix: session token refresh", ChangeCategory.BUGFIX, scope="auth"),
    ]
    security = [
        _make_item("fix: patch XSS vulnerability", ChangeCategory.SECURITY, importance=Importance.HIGH, scope="web"),
    ]
    perf = [
        _make_item("perf: optimize dashboard queries", ChangeCategory.PERFORMANCE, scope="dashboard"),
    ]
    improvements = [
        _make_item("Improve error messages", ChangeCategory.IMPROVEMENT, scope="core"),
    ]
    breaking = [
        _make_item(
            "feat(api)!: Remove legacy API endpoints", ChangeCategory.BREAKING,
            breaking=True, scope="api", description="The v1 endpoints have been removed",
        ),
    ]
    infra = [_make_item("ci: Update CI pipeline", ChangeCategory.INFRASTRUCTURE)]
    refactor = [_make_item("refactor(db): Refactor database layer", ChangeCategory.REFACTOR, scope="db")]

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


class TestFactExtraction:
    """Verifies the fact layer that bridges ReleaseNotes → narrative."""

    def test_produces_one_fact_per_source_item(self, rich_notes: ReleaseNotes):
        """GIVEN rich release notes WHEN extracting facts THEN 1:1 mapping."""
        facts = extract_facts(rich_notes)
        total_items = sum(len(g.items) for g in rich_notes.groups)
        assert len(facts) == total_items

    def test_strips_commit_prefixes(self, rich_notes: ReleaseNotes):
        """GIVEN items with conventional-commit prefixes WHEN extracting facts THEN prefixes removed."""
        facts = extract_facts(rich_notes)
        prefixes = ("feat:", "fix:", "perf:", "ci:", "refactor(")
        for fact in facts:
            assert not any(fact.text.lower().startswith(p) for p in prefixes)

    def test_preserves_source_traceability(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN extracting facts THEN every fact has source IDs."""
        facts = extract_facts(rich_notes)
        for fact in facts:
            assert len(fact.source_ids) >= 1

    def test_marks_highlights_and_breaking(self, rich_notes: ReleaseNotes):
        """GIVEN notes with highlights/breaking WHEN extracting THEN flags are set."""
        facts = extract_facts(rich_notes)
        assert any(f.is_highlight for f in facts)
        assert any(f.is_breaking for f in facts)

    def test_customer_mode_hides_internal_categories(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN extracting with customer_facing THEN internal categories hidden."""
        all_groups = extract_fact_groups(rich_notes, customer_facing=False)
        customer_groups = extract_fact_groups(rich_notes, customer_facing=True)
        assert len(customer_groups) < len(all_groups)
        customer_cats = {g.category for g in customer_groups}
        assert ChangeCategory.REFACTOR not in customer_cats
        assert ChangeCategory.INFRASTRUCTURE not in customer_cats

    def test_appends_description_to_fact_text(self):
        """GIVEN an item with a description WHEN extracting THEN description is included."""
        item = _make_item("Add OAuth", description="Full flow with PKCE")
        notes = ReleaseNotes(
            release_range=ReleaseRange(from_ref="a", to_ref="b"),
            groups=(ChangeGroup(category=ChangeCategory.FEATURE, items=(item,)),),
            total_changes=1,
        )
        facts = extract_facts(notes)
        assert "PKCE" in facts[0].text

    def test_collect_all_source_ids(self, rich_notes: ReleaseNotes):
        """GIVEN fact groups WHEN collecting source IDs THEN all items represented."""
        groups = extract_fact_groups(rich_notes)
        ids = collect_all_source_ids(groups)
        assert len(ids) > 0


# ── Narrative Composition ────────────────────────────────────────────────────


class TestNarrativeComposition:
    """Verifies that compose_narrative produces correct, grounded prose."""

    def test_overview_contains_app_name_version_and_counts(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN composing THEN overview has app name, version, and change count."""
        brief = compose_narrative(rich_notes)
        assert "TestApp" in brief.overview
        assert "2.1.0" in brief.overview
        assert str(brief.total_facts) in brief.overview

    def test_body_paragraphs_are_prose_not_bullets(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN composing THEN body is prose with sentences, not bullet lists."""
        brief = compose_narrative(rich_notes)
        assert len(brief.body_paragraphs) > 0
        for paragraph in brief.body_paragraphs:
            assert not paragraph.strip().startswith("-")
            assert not paragraph.strip().startswith("•")
            assert "." in paragraph

    def test_breaking_notice_generated(self, rich_notes: ReleaseNotes):
        """GIVEN notes with breaking changes WHEN composing THEN breaking notice present."""
        brief = compose_narrative(rich_notes)
        assert brief.breaking_notice
        assert "breaking" in brief.breaking_notice.lower()

    def test_fact_groups_and_source_ids_inspectable(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN composing THEN fact groups and source IDs are available."""
        brief = compose_narrative(rich_notes)
        assert len(brief.fact_groups) > 0
        assert len(brief.source_item_ids) > 0
        assert brief.total_facts == sum(g.count for g in brief.fact_groups)

    def test_empty_notes_produces_empty_narrative(self, empty_notes: ReleaseNotes):
        """GIVEN empty notes WHEN composing THEN minimal narrative with no facts."""
        brief = compose_narrative(empty_notes)
        assert "no notable changes" in brief.overview.lower()
        assert brief.total_facts == 0

    def test_customer_mode_hides_technical_details(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN composing customer narrative THEN no refactor/CI references."""
        brief = compose_narrative(rich_notes, customer_facing=True)
        assert brief.mode == "customer-narrative"
        full_text = brief.full_text.lower()
        assert "refactor" not in full_text
        assert "ci pipeline" not in full_text


# ── Claim Validation ─────────────────────────────────────────────────────────


class TestNarrativeValidation:
    """Verifies that the validator catches ungrounded claims."""

    def test_composed_narrative_passes_validation(self, rich_notes: ReleaseNotes):
        """GIVEN a properly composed narrative WHEN validating THEN no errors."""
        brief = compose_narrative(rich_notes)
        issues = validate_narrative(brief)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"

    def test_detects_forbidden_marketing_language(self, sample_range: ReleaseRange):
        """GIVEN a brief with marketing language WHEN validating THEN forbidden rules trigger."""
        brief = NarrativeBrief(
            release_range=sample_range,
            overview="This revolutionary release is a game-changer.",
            body_paragraphs=("It seamlessly integrates cutting-edge technology.",),
            total_facts=1,
            fact_groups=(
                FactGroup(
                    theme="Features", summary="1 feature added",
                    facts=(FactItem(text="Add widget", category=ChangeCategory.FEATURE, source_ids=("x",)),),
                    category=ChangeCategory.FEATURE,
                ),
            ),
            source_item_ids=frozenset({"x"}),
        )
        issues = validate_narrative(brief)
        error_rules = {i.rule for i in issues if i.severity == "error"}
        assert any("revolutionary" in r for r in error_rules)
        assert any("game_changer" in r for r in error_rules)
        assert any("seamless" in r for r in error_rules)

    def test_detects_fact_count_mismatch(self, sample_range: ReleaseRange):
        """GIVEN a brief with wrong total_facts WHEN validating THEN mismatch detected."""
        brief = NarrativeBrief(
            release_range=sample_range,
            overview="Overview",
            total_facts=999,
            fact_groups=(
                FactGroup(
                    theme="Features", summary="1 feature",
                    facts=(FactItem(text="Add x", category=ChangeCategory.FEATURE, source_ids=("x",)),),
                    category=ChangeCategory.FEATURE,
                ),
            ),
            source_item_ids=frozenset({"x"}),
        )
        issues = validate_narrative(brief)
        assert any("fact_count_mismatch" in i.rule for i in issues)

    def test_detects_phantom_category(self, sample_range: ReleaseRange):
        """GIVEN text referencing security but no security facts WHEN validating THEN phantom detected."""
        brief = NarrativeBrief(
            release_range=sample_range,
            overview="This includes a security update for better protection.",
            total_facts=1,
            fact_groups=(
                FactGroup(
                    theme="Features", summary="1 feature",
                    facts=(FactItem(text="Add x", category=ChangeCategory.FEATURE, source_ids=("x",)),),
                    category=ChangeCategory.FEATURE,
                ),
            ),
            source_item_ids=frozenset({"x"}),
        )
        issues = validate_narrative(brief)
        assert any("phantom_category" in i.rule for i in issues)


# ── Rendering ────────────────────────────────────────────────────────────────


class TestNarrativeRendering:
    """Verifies that renderers produce correct output formats."""

    def test_markdown_contains_headings_and_prose(self, rich_notes: ReleaseNotes):
        """GIVEN a composed brief WHEN rendering markdown THEN output has headings, app name, prose."""
        brief = compose_narrative(rich_notes)
        output = NarrativeMarkdownRenderer().render(brief)
        assert "# TestApp" in output
        assert "2.1.0" in output
        assert "## Overview" in output or "## What" in output
        assert "verified facts" in output.lower()

    def test_markdown_has_no_bullet_lists_in_body(self, rich_notes: ReleaseNotes):
        """GIVEN a composed brief WHEN rendering THEN body is prose paragraphs, not bullet lists."""
        brief = compose_narrative(rich_notes)
        output = NarrativeMarkdownRenderer().render(brief)
        body_lines = [
            line for line in output.split("\n")
            if line.strip() and not line.startswith("#") and not line.startswith("*")
            and not line.startswith("---") and not line.startswith("|")
        ]
        for line in body_lines:
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("• "):
                assert "ReleasePilot" in line or "verified" in line, \
                    f"Unexpected bullet point in narrative: {line}"

    def test_markdown_breaking_section(self, rich_notes: ReleaseNotes):
        """GIVEN notes with breaking changes WHEN rendering THEN breaking section present."""
        brief = compose_narrative(rich_notes)
        output = NarrativeMarkdownRenderer().render(brief)
        assert "Important Changes" in output or "breaking" in output.lower()

    def test_json_output_structure(self, rich_notes: ReleaseNotes):
        """GIVEN a composed brief WHEN rendering JSON THEN includes fact layer for auditability."""
        brief = compose_narrative(rich_notes)
        parsed = json.loads(NarrativeMarkdownRenderer().render_json(brief))
        assert parsed["type"] == "narrative_brief"
        assert parsed["mode"] == "narrative"
        assert isinstance(parsed["fact_groups"], list)
        assert parsed["total_facts"] > 0

    @pytest.mark.parametrize("customer_facing,expected_mode", [
        (False, "narrative"),
        (True, "customer-narrative"),
    ])
    def test_json_mode_matches_composition(self, rich_notes, customer_facing, expected_mode):
        """GIVEN customer_facing flag WHEN rendering JSON THEN mode field matches."""
        brief = compose_narrative(rich_notes, customer_facing=customer_facing)
        parsed = json.loads(NarrativeMarkdownRenderer().render_json(brief))
        assert parsed["mode"] == expected_mode

    def test_plaintext_rendering(self, rich_notes: ReleaseNotes):
        """GIVEN a composed brief WHEN rendering plaintext THEN produces readable terminal output."""
        brief = compose_narrative(rich_notes)
        output = NarrativePlaintextRenderer().render(brief)
        assert "TestApp" in output
        assert "Release Summary" in output
        assert "changes from" in output.lower() or "source items" in output.lower()

    def test_empty_narrative_renders(self, empty_notes: ReleaseNotes):
        """GIVEN empty notes WHEN rendering plaintext THEN graceful 'no changes' output."""
        brief = compose_narrative(empty_notes)
        output = NarrativePlaintextRenderer().render(brief)
        assert "no notable changes" in output.lower()

    def test_pdf_produces_valid_bytes(self, rich_notes: ReleaseNotes):
        """GIVEN a composed brief WHEN rendering PDF THEN valid PDF bytes produced."""
        from releasepilot.rendering.narrative_pdf import NarrativePdfRenderer
        brief = compose_narrative(rich_notes)
        data = NarrativePdfRenderer().render_bytes(brief)
        assert data[:5] == b"%PDF-"
        assert len(data) > 1000

    def test_docx_produces_valid_bytes(self, rich_notes: ReleaseNotes):
        """GIVEN a composed brief WHEN rendering DOCX THEN valid DOCX (ZIP) bytes produced."""
        from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer
        brief = compose_narrative(rich_notes)
        data = NarrativeDocxRenderer().render_bytes(brief)
        assert data[:2] == b"PK"
        assert len(data) > 1000

    @pytest.mark.parametrize("customer_facing", [False, True])
    def test_pdf_customer_mode(self, rich_notes: ReleaseNotes, customer_facing: bool):
        """GIVEN either narrative mode WHEN rendering PDF THEN produces valid output."""
        from releasepilot.rendering.narrative_pdf import NarrativePdfRenderer
        brief = compose_narrative(rich_notes, customer_facing=customer_facing)
        data = NarrativePdfRenderer().render_bytes(brief)
        assert data[:5] == b"%PDF-"

    @pytest.mark.parametrize("customer_facing", [False, True])
    def test_docx_customer_mode(self, rich_notes: ReleaseNotes, customer_facing: bool):
        """GIVEN either narrative mode WHEN rendering DOCX THEN produces valid output."""
        from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer
        brief = compose_narrative(rich_notes, customer_facing=customer_facing)
        data = NarrativeDocxRenderer().render_bytes(brief)
        assert data[:2] == b"PK"


# ── NarrativeBrief Model ────────────────────────────────────────────────────


class TestNarrativeBriefModel:
    """Verifies NarrativeBrief computed properties."""

    @pytest.mark.parametrize("mode,expected_label", [
        ("narrative", "Release Summary"),
        ("customer-narrative", "Product Update"),
    ])
    def test_report_title(self, sample_range, mode, expected_label):
        brief = NarrativeBrief(release_range=sample_range, overview="test", mode=mode)
        assert expected_label in brief.report_title
        assert "v2.1.0" in brief.report_title

    def test_full_text_concatenates_all_sections(self, sample_range: ReleaseRange):
        brief = NarrativeBrief(
            release_range=sample_range,
            overview="Overview.",
            body_paragraphs=("Body one.", "Body two."),
            breaking_notice="Breaking.",
            closing="Closing.",
        )
        full = brief.full_text
        for expected in ("Overview.", "Body one.", "Body two.", "Breaking.", "Closing."):
            assert expected in full


# ── Grounding Guarantees ─────────────────────────────────────────────────────


class TestGroundingGuarantees:
    """End-to-end truthfulness: every fact traces to real source data."""

    def test_every_fact_traces_to_source_item(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN composing THEN every source_id maps to a real ChangeItem."""
        brief = compose_narrative(rich_notes)
        all_item_ids = {item.id for g in rich_notes.groups for item in g.items}
        for group in brief.fact_groups:
            for fact in group.facts:
                for sid in fact.source_ids:
                    assert sid in all_item_ids, f"Fact references unknown source: {sid}"

    def test_customer_narrative_passes_grounding(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN composing customer narrative THEN validation passes."""
        brief = compose_narrative(rich_notes, customer_facing=True)
        errors = [i for i in validate_narrative(brief) if i.severity == "error"]
        assert len(errors) == 0

    def test_empty_release_passes_grounding(self, empty_notes: ReleaseNotes):
        brief = compose_narrative(empty_notes)
        errors = [i for i in validate_narrative(brief) if i.severity == "error"]
        assert len(errors) == 0


# ── CLI Integration ──────────────────────────────────────────────────────────


class TestNarrativeCLI:
    """Verifies that narrative audiences work through the CLI."""

    def test_narrative_audience_in_choices(self):
        from releasepilot.cli.app import _ALL_AUDIENCES
        assert "narrative" in _ALL_AUDIENCES
        assert "customer-narrative" in _ALL_AUDIENCES

    def test_narrative_format_choices_include_pdf_docx(self):
        """GIVEN the guided workflow THEN narrative format choices include PDF and DOCX."""
        from releasepilot.cli.guide import _FORMAT_CHOICES_NARRATIVE
        formats = [f[1] for f in _FORMAT_CHOICES_NARRATIVE]
        assert "pdf" in formats
        assert "docx" in formats
        assert "markdown" in formats

    def test_generate_narrative_markdown(self, tmp_path):
        """GIVEN a structured source file WHEN running generate --audience narrative THEN prose output."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({
            "changes": [
                {"title": "Add user search", "category": "feature", "scope": "search"},
                {"title": "Fix login bug", "category": "bugfix", "scope": "auth"},
            ]
        }))
        result = CliRunner().invoke(cli, [
            "generate", "--source-file", str(source),
            "--audience", "narrative", "--from", "v1.0.0",
        ])
        assert result.exit_code == 0, result.output
        assert "Release Summary" in result.output or "Overview" in result.output

    def test_generate_customer_narrative(self, tmp_path):
        """GIVEN source file WHEN running generate --audience customer-narrative THEN customer prose."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({
            "changes": [
                {"title": "Add dark mode", "category": "feature"},
                {"title": "Improve loading speed", "category": "performance"},
            ]
        }))
        result = CliRunner().invoke(cli, [
            "generate", "--source-file", str(source),
            "--audience", "customer-narrative", "--from", "v1.0.0",
        ])
        assert result.exit_code == 0, result.output
        assert "Product Update" in result.output or "What's Changed" in result.output

    def test_generate_narrative_json(self, tmp_path):
        """GIVEN source file WHEN running generate --audience narrative --format json THEN valid JSON."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({
            "changes": [{"title": "Add export feature", "category": "feature"}]
        }))
        result = CliRunner().invoke(cli, [
            "generate", "--source-file", str(source),
            "--audience", "narrative", "--format", "json", "--from", "v1.0.0",
        ])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["type"] == "narrative_brief"

    def test_export_narrative(self, tmp_path):
        """GIVEN source file WHEN running export --audience narrative THEN file written."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({
            "changes": [{"title": "Add billing module", "category": "feature"}]
        }))
        output = tmp_path / "narrative.md"
        result = CliRunner().invoke(cli, [
            "export", "--source-file", str(source),
            "--audience", "narrative", "-o", str(output), "--from", "v1.0.0",
        ])
        assert result.exit_code == 0, result.output
        assert "Release Summary" in output.read_text() or "Overview" in output.read_text()

    def test_generate_narrative_pdf(self, tmp_path):
        """GIVEN source file WHEN running generate --audience narrative --format pdf THEN PDF written."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({
            "changes": [{"title": "Add search", "category": "feature"}]
        }))
        result = CliRunner().invoke(cli, [
            "generate", "--source-file", str(source),
            "--audience", "narrative", "--format", "pdf", "--from", "v1.0.0",
        ])
        assert result.exit_code == 0, result.output
        assert "Written to" in result.output

    def test_generate_narrative_docx(self, tmp_path):
        """GIVEN source file WHEN running generate --audience narrative --format docx THEN DOCX written."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({
            "changes": [{"title": "Add dashboard", "category": "feature"}]
        }))
        result = CliRunner().invoke(cli, [
            "generate", "--source-file", str(source),
            "--audience", "narrative", "--format", "docx", "--from", "v1.0.0",
        ])
        assert result.exit_code == 0, result.output
        assert "Written to" in result.output

    def test_export_narrative_pdf(self, tmp_path):
        """GIVEN source file WHEN running export --audience narrative --format pdf THEN PDF file written."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({
            "changes": [{"title": "Add notifications", "category": "feature"}]
        }))
        output = tmp_path / "narrative.pdf"
        result = CliRunner().invoke(cli, [
            "export", "--source-file", str(source),
            "--audience", "narrative", "--format", "pdf",
            "-o", str(output), "--from", "v1.0.0",
        ])
        assert result.exit_code == 0, result.output
        data = output.read_bytes()
        assert data[:5] == b"%PDF-"

    def test_export_customer_narrative_docx(self, tmp_path):
        """GIVEN source file WHEN exporting customer-narrative as DOCX THEN valid DOCX."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        source = tmp_path / "changes.json"
        source.write_text(json.dumps({
            "changes": [{"title": "Improve onboarding flow", "category": "improvement"}]
        }))
        output = tmp_path / "update.docx"
        result = CliRunner().invoke(cli, [
            "export", "--source-file", str(source),
            "--audience", "customer-narrative", "--format", "docx",
            "-o", str(output), "--from", "v1.0.0",
        ])
        assert result.exit_code == 0, result.output
        data = output.read_bytes()
        assert data[:2] == b"PK"


# ── Isolation / Non-Regression ───────────────────────────────────────────────


class TestNarrativeIsolation:
    """Verifies that the narrative pipeline does not affect the standard pipeline."""

    def test_standard_pipeline_still_produces_bullets(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN rendering with standard renderer THEN bullet output unchanged."""
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.markdown import MarkdownRenderer
        output = MarkdownRenderer().render(rich_notes, RenderConfig())
        assert "- " in output

    def test_compose_does_not_mutate_input(self, rich_notes: ReleaseNotes):
        """GIVEN rich notes WHEN composing narrative THEN input ReleaseNotes unchanged."""
        original_total = rich_notes.total_changes
        original_groups = len(rich_notes.groups)
        compose_narrative(rich_notes)
        assert rich_notes.total_changes == original_total
        assert len(rich_notes.groups) == original_groups

    def test_narrative_and_standard_produce_different_output(self, rich_notes: ReleaseNotes):
        """GIVEN same notes WHEN rendering both ways THEN outputs are distinct."""
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.markdown import MarkdownRenderer
        standard = MarkdownRenderer().render(rich_notes, RenderConfig())
        narrative = NarrativeMarkdownRenderer().render(compose_narrative(rich_notes))
        assert standard != narrative
        assert standard.count("\n- ") > narrative.count("\n- ")


# ── Audience Views ───────────────────────────────────────────────────────────


class TestNarrativeAudienceViews:
    """Verifies that narrative audience transforms work through apply_audience."""

    def test_narrative_preserves_all_categories(self, rich_notes: ReleaseNotes):
        from releasepilot.audience.views import apply_audience
        result = apply_audience(rich_notes, Audience.NARRATIVE)
        assert {g.category for g in result.groups} == {g.category for g in rich_notes.groups}

    def test_customer_narrative_hides_internal(self, rich_notes: ReleaseNotes):
        from releasepilot.audience.views import apply_audience
        result = apply_audience(rich_notes, Audience.CUSTOMER_NARRATIVE)
        result_cats = {g.category for g in result.groups}
        assert ChangeCategory.REFACTOR not in result_cats
        assert ChangeCategory.INFRASTRUCTURE not in result_cats
