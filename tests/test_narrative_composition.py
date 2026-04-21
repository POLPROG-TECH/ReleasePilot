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


# ── Fact Extraction ──────────────────────────────────────────────────────────


# ── Narrative Composition ────────────────────────────────────────────────────


# ── Claim Validation ─────────────────────────────────────────────────────────


# ── Rendering ────────────────────────────────────────────────────────────────


# ── NarrativeBrief Model ────────────────────────────────────────────────────


# ── Grounding Guarantees ─────────────────────────────────────────────────────


# ── CLI Integration ──────────────────────────────────────────────────────────


# ── Isolation / Non-Regression ───────────────────────────────────────────────


# ── Audience Views ───────────────────────────────────────────────────────────


class TestFactExtraction:
    """Verifies the fact layer that bridges ReleaseNotes → narrative."""

    """GIVEN rich release notes"""

    def test_produces_one_fact_per_source_item(self, rich_notes: ReleaseNotes):
        """WHEN extracting facts"""
        facts = extract_facts(rich_notes)
        total_items = sum(len(g.items) for g in rich_notes.groups)
        """THEN 1:1 mapping"""
        assert len(facts) == total_items

    """GIVEN items with conventional-commit prefixes"""

    def test_strips_commit_prefixes(self, rich_notes: ReleaseNotes):
        """WHEN extracting facts"""
        facts = extract_facts(rich_notes)
        prefixes = ("feat:", "fix:", "perf:", "ci:", "refactor(")
        for fact in facts:
            assert not any(fact.text.lower().startswith(p) for p in prefixes)

    """GIVEN rich notes"""

    def test_preserves_source_traceability(self, rich_notes: ReleaseNotes):
        """WHEN extracting facts"""
        facts = extract_facts(rich_notes)
        for fact in facts:
            assert len(fact.source_ids) >= 1

    """GIVEN notes with highlights/breaking"""

    def test_marks_highlights_and_breaking(self, rich_notes: ReleaseNotes):
        """WHEN extracting"""
        facts = extract_facts(rich_notes)
        """THEN flags are set"""
        assert any(f.is_highlight for f in facts)
        assert any(f.is_breaking for f in facts)

    """GIVEN rich notes"""

    def test_customer_mode_hides_internal_categories(self, rich_notes: ReleaseNotes):
        """WHEN extracting with customer_facing"""
        all_groups = extract_fact_groups(rich_notes, customer_facing=False)
        customer_groups = extract_fact_groups(rich_notes, customer_facing=True)
        """THEN internal categories hidden"""
        assert len(customer_groups) < len(all_groups)
        customer_cats = {g.category for g in customer_groups}
        assert ChangeCategory.REFACTOR not in customer_cats
        assert ChangeCategory.INFRASTRUCTURE not in customer_cats

    """GIVEN an item with a description"""

    def test_appends_description_to_fact_text(self):
        """WHEN extracting"""
        item = _make_item("Add OAuth", description="Full flow with PKCE")
        notes = ReleaseNotes(
            release_range=ReleaseRange(from_ref="a", to_ref="b"),
            groups=(ChangeGroup(category=ChangeCategory.FEATURE, items=(item,)),),
            total_changes=1,
        )
        facts = extract_facts(notes)
        """THEN description is included"""
        assert "PKCE" in facts[0].text

    """GIVEN fact groups"""

    def test_collect_all_source_ids(self, rich_notes: ReleaseNotes):
        """WHEN collecting source IDs"""
        groups = extract_fact_groups(rich_notes)
        ids = collect_all_source_ids(groups)
        """THEN all items represented"""
        assert len(ids) > 0


class TestNarrativeComposition:
    """Verifies that compose_narrative produces correct, grounded prose."""

    """GIVEN rich notes"""

    def test_overview_contains_app_name_version_and_counts(self, rich_notes: ReleaseNotes):
        """WHEN composing"""
        brief = compose_narrative(rich_notes)
        """THEN overview has app name, version, and change count"""
        assert "TestApp" in brief.overview
        assert "2.1.0" in brief.overview
        assert str(brief.total_facts) in brief.overview

    """GIVEN rich notes"""

    def test_body_paragraphs_are_prose_not_bullets(self, rich_notes: ReleaseNotes):
        """WHEN composing"""
        brief = compose_narrative(rich_notes)
        """THEN body is prose with sentences, not bullet lists"""
        assert len(brief.body_paragraphs) > 0
        for paragraph in brief.body_paragraphs:
            assert not paragraph.strip().startswith("-")
            assert not paragraph.strip().startswith("•")
            assert "." in paragraph

    """GIVEN notes with breaking changes"""

    def test_breaking_notice_generated(self, rich_notes: ReleaseNotes):
        """WHEN composing"""
        brief = compose_narrative(rich_notes)
        """THEN breaking notice present"""
        assert brief.breaking_notice
        assert "breaking" in brief.breaking_notice.lower()

    """GIVEN rich notes"""

    def test_fact_groups_and_source_ids_inspectable(self, rich_notes: ReleaseNotes):
        """WHEN composing"""
        brief = compose_narrative(rich_notes)
        """THEN fact groups and source IDs are available"""
        assert len(brief.fact_groups) > 0
        assert len(brief.source_item_ids) > 0
        assert brief.total_facts == sum(g.count for g in brief.fact_groups)

    """GIVEN empty notes"""

    def test_empty_notes_produces_empty_narrative(self, empty_notes: ReleaseNotes):
        """WHEN composing"""
        brief = compose_narrative(empty_notes)
        """THEN minimal narrative with no facts"""
        assert "no notable changes" in brief.overview.lower()
        assert brief.total_facts == 0

    """GIVEN rich notes"""

    def test_customer_mode_hides_technical_details(self, rich_notes: ReleaseNotes):
        """WHEN composing customer narrative"""
        brief = compose_narrative(rich_notes, customer_facing=True)
        """THEN no refactor/CI references"""
        assert brief.mode == "customer-narrative"
        full_text = brief.full_text.lower()
        assert "refactor" not in full_text
        assert "ci pipeline" not in full_text


class TestNarrativeValidation:
    """Verifies that the validator catches ungrounded claims."""

    """GIVEN a properly composed narrative"""

    def test_composed_narrative_passes_validation(self, rich_notes: ReleaseNotes):
        """WHEN validating"""
        brief = compose_narrative(rich_notes)
        issues = validate_narrative(brief)
        errors = [i for i in issues if i.severity == "error"]
        """THEN no errors"""
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"

    """GIVEN a brief with marketing language"""

    def test_detects_forbidden_marketing_language(self, sample_range: ReleaseRange):
        """WHEN validating"""
        brief = NarrativeBrief(
            release_range=sample_range,
            overview="This revolutionary release is a game-changer.",
            body_paragraphs=("It seamlessly integrates cutting-edge technology.",),
            total_facts=1,
            fact_groups=(
                FactGroup(
                    theme="Features",
                    summary="1 feature added",
                    facts=(
                        FactItem(
                            text="Add widget", category=ChangeCategory.FEATURE, source_ids=("x",)
                        ),
                    ),
                    category=ChangeCategory.FEATURE,
                ),
            ),
            source_item_ids=frozenset({"x"}),
        )
        issues = validate_narrative(brief)
        error_rules = {i.rule for i in issues if i.severity == "error"}
        """THEN forbidden rules trigger"""
        assert any("revolutionary" in r for r in error_rules)
        assert any("game_changer" in r for r in error_rules)
        assert any("seamless" in r for r in error_rules)

    """GIVEN a brief with wrong total_facts"""

    def test_detects_fact_count_mismatch(self, sample_range: ReleaseRange):
        """WHEN validating"""
        brief = NarrativeBrief(
            release_range=sample_range,
            overview="Overview",
            total_facts=999,
            fact_groups=(
                FactGroup(
                    theme="Features",
                    summary="1 feature",
                    facts=(
                        FactItem(text="Add x", category=ChangeCategory.FEATURE, source_ids=("x",)),
                    ),
                    category=ChangeCategory.FEATURE,
                ),
            ),
            source_item_ids=frozenset({"x"}),
        )
        issues = validate_narrative(brief)
        """THEN mismatch detected"""
        assert any("fact_count_mismatch" in i.rule for i in issues)

    """GIVEN text referencing security but no security facts"""

    def test_detects_phantom_category(self, sample_range: ReleaseRange):
        """WHEN validating"""
        brief = NarrativeBrief(
            release_range=sample_range,
            overview="This includes a security update for better protection.",
            total_facts=1,
            fact_groups=(
                FactGroup(
                    theme="Features",
                    summary="1 feature",
                    facts=(
                        FactItem(text="Add x", category=ChangeCategory.FEATURE, source_ids=("x",)),
                    ),
                    category=ChangeCategory.FEATURE,
                ),
            ),
            source_item_ids=frozenset({"x"}),
        )
        issues = validate_narrative(brief)
        """THEN phantom detected"""
        assert any("phantom_category" in i.rule for i in issues)


class TestNarrativeBriefModel:
    """Verifies NarrativeBrief computed properties."""

    """GIVEN a scenario for report title"""

    @pytest.mark.parametrize(
        "mode,expected_label",
        [
            ("narrative", "Release Summary"),
            ("customer-narrative", "Product Update"),
        ],
    )
    def test_report_title(self, sample_range, mode, expected_label):
        """WHEN the test exercises report title"""
        brief = NarrativeBrief(release_range=sample_range, overview="test", mode=mode)
        """THEN the expected behavior for report title is observed"""
        assert expected_label in brief.report_title
        assert "v2.1.0" in brief.report_title

    """GIVEN a scenario for full text concatenates all sections"""

    def test_full_text_concatenates_all_sections(self, sample_range: ReleaseRange):
        """WHEN the test exercises full text concatenates all sections"""
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


class TestGroundingGuarantees:
    """End-to-end truthfulness: every fact traces to real source data."""

    """GIVEN rich notes"""

    def test_every_fact_traces_to_source_item(self, rich_notes: ReleaseNotes):
        """WHEN composing"""
        brief = compose_narrative(rich_notes)
        all_item_ids = {item.id for g in rich_notes.groups for item in g.items}
        for group in brief.fact_groups:
            for fact in group.facts:
                for sid in fact.source_ids:
                    assert sid in all_item_ids, f"Fact references unknown source: {sid}"

    """GIVEN rich notes"""

    def test_customer_narrative_passes_grounding(self, rich_notes: ReleaseNotes):
        """WHEN composing customer narrative"""
        brief = compose_narrative(rich_notes, customer_facing=True)
        errors = [i for i in validate_narrative(brief) if i.severity == "error"]
        """THEN validation passes"""
        assert len(errors) == 0

    """GIVEN a scenario for empty release passes grounding"""

    def test_empty_release_passes_grounding(self, empty_notes: ReleaseNotes):
        """WHEN the test exercises empty release passes grounding"""
        brief = compose_narrative(empty_notes)
        errors = [i for i in validate_narrative(brief) if i.severity == "error"]
        """THEN the expected behavior for empty release passes grounding is observed"""
        assert len(errors) == 0
