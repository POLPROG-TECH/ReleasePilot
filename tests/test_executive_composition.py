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

from datetime import date

import pytest

from releasepilot.audience.executive import (
    ExecutiveBrief,
    compose_executive_brief,
)
from releasepilot.domain.enums import Audience, ChangeCategory, Importance
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


# ── ExecutiveBrief composition tests ─────────────────────────────────────────


# ── Executive Markdown renderer tests ────────────────────────────────────────


# ── Executive PDF renderer tests ─────────────────────────────────────────────


# ── Executive DOCX renderer tests ────────────────────────────────────────────


# ── CLI integration tests ────────────────────────────────────────────────────


# ── Audience view tests ──────────────────────────────────────────────────────


class TestComposeExecutiveBrief:
    """Scenarios for composing an executive brief from mixed release notes."""

    """GIVEN a composed executive brief"""

    def test_returns_executive_brief(self, sample_brief: ExecutiveBrief):
        """WHEN checking its type"""

        """THEN it is an ExecutiveBrief instance"""
        assert isinstance(sample_brief, ExecutiveBrief)

    """GIVEN a composed executive brief"""

    def test_executive_summary_is_non_empty(self, sample_brief: ExecutiveBrief):
        """WHEN checking the summary length"""

        """THEN it exceeds 50 characters"""
        assert len(sample_brief.executive_summary) > 50

    """GIVEN a composed executive brief"""

    def test_summary_mentions_capabilities(self, sample_brief: ExecutiveBrief):
        """WHEN examining the summary"""

        """THEN it mentions capabilities"""
        assert "capabilit" in sample_brief.executive_summary.lower()

    """GIVEN a composed executive brief"""

    def test_summary_mentions_security(self, sample_brief: ExecutiveBrief):
        """WHEN examining the summary"""

        """THEN it mentions security"""
        assert "security" in sample_brief.executive_summary.lower()

    """GIVEN a composed executive brief"""

    def test_summary_mentions_attention(self, sample_brief: ExecutiveBrief):
        """WHEN examining the summary"""

        """THEN it mentions attention items"""
        assert "attention" in sample_brief.executive_summary.lower()

    """GIVEN a composed executive brief"""

    def test_key_achievements_non_empty(self, sample_brief: ExecutiveBrief):
        """WHEN checking key achievements"""

        """THEN at least one exists"""
        assert len(sample_brief.key_achievements) >= 1

    """GIVEN a composed executive brief"""

    def test_key_achievements_max_7(self, sample_brief: ExecutiveBrief):
        """WHEN counting key achievements"""

        """THEN there are at most seven"""
        assert len(sample_brief.key_achievements) <= 7

    """GIVEN a composed executive brief"""

    def test_impact_areas_non_empty(self, sample_brief: ExecutiveBrief):
        """WHEN checking impact areas"""

        """THEN at least three exist"""
        assert len(sample_brief.impact_areas) >= 3

    """GIVEN a composed executive brief"""

    def test_impact_areas_have_business_titles(self, sample_brief: ExecutiveBrief):
        titles = {a.title for a in sample_brief.impact_areas}

        """WHEN checking impact area titles"""

        """THEN business-oriented titles are used"""
        # Should have business-oriented titles, not technical category names
        assert "New Capabilities" in titles
        assert "Quality & Reliability" in titles

    """GIVEN a composed executive brief"""

    def test_impact_areas_have_summaries(self, sample_brief: ExecutiveBrief):
        """WHEN checking impact area summaries"""

        """THEN each has a meaningful summary"""
        for area in sample_brief.impact_areas:
            assert len(area.summary) > 10

    """GIVEN a composed executive brief"""

    def test_risks_from_breaking_changes(self, sample_brief: ExecutiveBrief):
        """WHEN checking risks"""

        """THEN breaking changes produce API-related risks"""
        assert len(sample_brief.risks) >= 1
        # Should mention API endpoints removal
        any_api_risk = any(
            "api" in r.lower() or "endpoint" in r.lower() for r in sample_brief.risks
        )
        assert any_api_risk

    """GIVEN a composed executive brief"""

    def test_risks_include_deprecations(self, sample_brief: ExecutiveBrief):
        """WHEN checking risks"""

        """THEN deprecations are included"""
        any_deprecation = any("deprecat" in r.lower() for r in sample_brief.risks)
        assert any_deprecation

    """GIVEN a composed executive brief"""

    def test_next_steps_non_empty(self, sample_brief: ExecutiveBrief):
        """WHEN checking next steps"""

        """THEN at least two exist"""
        assert len(sample_brief.next_steps) >= 2

    """GIVEN a composed executive brief"""

    def test_next_steps_mention_breaking_communication(self, sample_brief: ExecutiveBrief):
        """WHEN checking next steps"""

        """THEN breaking change communication is mentioned"""
        any_breaking_step = any("breaking" in s.lower() for s in sample_brief.next_steps)
        assert any_breaking_step

    """GIVEN a composed executive brief"""

    def test_next_steps_mention_security(self, sample_brief: ExecutiveBrief):
        """WHEN checking next steps"""

        """THEN security follow-up is mentioned"""
        any_security_step = any("security" in s.lower() for s in sample_brief.next_steps)
        assert any_security_step

    """GIVEN a composed executive brief"""

    def test_metrics_has_total_changes(self, sample_brief: ExecutiveBrief):
        """WHEN reading metrics"""

        """THEN total_changes equals 10"""
        assert sample_brief.metrics["total_changes"] == 10

    """GIVEN a composed executive brief"""

    def test_metrics_has_features(self, sample_brief: ExecutiveBrief):
        """WHEN reading metrics"""

        """THEN features count equals 3"""
        assert sample_brief.metrics["features"] == 3

    """GIVEN a composed executive brief"""

    def test_metrics_has_breaking(self, sample_brief: ExecutiveBrief):
        """WHEN reading metrics"""

        """THEN breaking count equals 1"""
        assert sample_brief.metrics["breaking"] == 1

    """GIVEN a composed executive brief"""

    def test_report_title_includes_version(self, sample_brief: ExecutiveBrief):
        """WHEN checking the report title"""

        """THEN it includes the version number"""
        assert "3.0.0" in sample_brief.report_title

    """GIVEN a composed executive brief"""

    def test_report_date_formatted(self, sample_brief: ExecutiveBrief):
        """WHEN checking the report date"""

        """THEN it contains the month name"""
        assert "March" in sample_brief.report_date


class TestBusinessLanguageTransformation:
    """Scenarios for business-language transformation of commit titles."""

    """GIVEN a composed executive brief"""

    def test_conventional_prefix_stripped(self, sample_brief: ExecutiveBrief):
        # "feat: add OAuth2 authentication" should become "Add OAuth2 authentication"
        all_items = []
        for area in sample_brief.impact_areas:
            all_items.extend(area.items)

        """WHEN checking impact area items"""

        """THEN conventional commit prefixes are stripped"""
        # No items should start with "feat:", "fix:", etc.
        for item in all_items:
            assert not item.startswith("feat:")
            assert not item.startswith("fix:")
            assert not item.startswith("perf:")

    """GIVEN a composed executive brief"""

    def test_titles_capitalized(self, sample_brief: ExecutiveBrief):
        """WHEN checking item titles"""

        """THEN each title starts with an uppercase letter"""
        for area in sample_brief.impact_areas:
            for item in area.items:
                assert item[0].isupper(), f"Expected capitalized: {item}"


class TestEmptyRelease:
    """Scenarios for composing a brief from empty release notes."""

    """GIVEN release notes with zero changes"""

    def test_empty_notes_produce_valid_brief(self):
        empty_notes = ReleaseNotes(
            release_range=ReleaseRange(from_ref="v1.0", to_ref="HEAD"),
            groups=(),
            total_changes=0,
        )

        """WHEN composing an executive brief"""
        brief = compose_executive_brief(empty_notes)

        """THEN a valid brief with appropriate defaults is produced"""
        assert isinstance(brief, ExecutiveBrief)
        assert "0 changes" in brief.executive_summary or "change" in brief.executive_summary.lower()
        assert len(brief.impact_areas) == 0
        assert len(brief.risks) == 0


class TestExecutiveAudienceView:
    """Scenarios for executive audience view filtering."""

    """GIVEN release notes with a refactor group"""

    def test_executive_view_filters_refactors(self, sample_notes: ReleaseNotes):
        from releasepilot.audience.views import apply_audience

        # Add a refactor group to sample_notes
        refactor_group = ChangeGroup(
            category=ChangeCategory.REFACTOR,
            items=(_make_item("refactor auth module", ChangeCategory.REFACTOR),),
        )
        notes_with_refactor = ReleaseNotes(
            release_range=sample_notes.release_range,
            groups=sample_notes.groups + (refactor_group,),
            highlights=sample_notes.highlights,
            breaking_changes=sample_notes.breaking_changes,
            total_changes=sample_notes.total_changes + 1,
        )

        """WHEN applying executive audience filter"""
        filtered = apply_audience(notes_with_refactor, Audience.EXECUTIVE)
        categories = {g.category for g in filtered.groups}

        """THEN refactor and infrastructure categories are excluded"""
        assert ChangeCategory.REFACTOR not in categories
        assert ChangeCategory.INFRASTRUCTURE not in categories

    """GIVEN release notes with features"""

    def test_executive_view_keeps_features(self, sample_notes: ReleaseNotes):
        from releasepilot.audience.views import apply_audience

        """WHEN applying executive audience filter"""
        filtered = apply_audience(sample_notes, Audience.EXECUTIVE)
        categories = {g.category for g in filtered.groups}

        """THEN feature category is preserved"""
        assert ChangeCategory.FEATURE in categories

    """GIVEN release notes with security changes"""

    def test_executive_view_keeps_security(self, sample_notes: ReleaseNotes):
        from releasepilot.audience.views import apply_audience

        """WHEN applying executive audience filter"""
        filtered = apply_audience(sample_notes, Audience.EXECUTIVE)
        categories = {g.category for g in filtered.groups}

        """THEN security category is preserved"""
        assert ChangeCategory.SECURITY in categories
