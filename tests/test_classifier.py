"""Tests for the classification engine."""

from __future__ import annotations

from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import ChangeItem
from releasepilot.processing.classifier import classify


class TestConventionalCommitParsing:
    """Scenarios for conventional commit parsing."""

    def test_feat_type(self):
        """GIVEN a conventional commit with feat type."""
        item = ChangeItem(id="1", title="feat: add login page", raw_message="feat: add login page")

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as FEATURE."""
        assert result[0].category == ChangeCategory.FEATURE
        assert result[0].title == "add login page"

    def test_fix_type_with_scope(self):
        """GIVEN a conventional commit with fix type and scope."""
        item = ChangeItem(
            id="2",
            title="fix(auth): resolve token expiry",
            raw_message="fix(auth): resolve token expiry",
        )

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as BUGFIX with correct scope."""
        assert result[0].category == ChangeCategory.BUGFIX
        assert result[0].scope == "auth"
        assert result[0].title == "resolve token expiry"

    def test_breaking_change_with_bang(self):
        """GIVEN a conventional commit with breaking change indicator."""
        item = ChangeItem(
            id="3",
            title="feat(api)!: remove v1 endpoints",
            raw_message="feat(api)!: remove v1 endpoints",
        )

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as BREAKING with high importance."""
        assert result[0].category == ChangeCategory.BREAKING
        assert result[0].is_breaking is True
        assert result[0].importance == Importance.HIGH

    def test_breaking_change_footer(self):
        """GIVEN a commit with BREAKING CHANGE in the body."""
        item = ChangeItem(
            id="4",
            title="feat: new auth flow",
            raw_message="feat: new auth flow\n\nBREAKING CHANGE: old tokens invalidated",
        )

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as BREAKING."""
        assert result[0].category == ChangeCategory.BREAKING
        assert result[0].is_breaking is True

    def test_perf_type(self):
        """GIVEN a perf conventional commit."""
        item = ChangeItem(id="5", title="perf: optimize query", raw_message="perf: optimize query")

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as PERFORMANCE."""
        assert result[0].category == ChangeCategory.PERFORMANCE

    def test_docs_type(self):
        """GIVEN a docs conventional commit."""
        item = ChangeItem(id="6", title="docs: update README", raw_message="docs: update README")

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as DOCUMENTATION."""
        assert result[0].category == ChangeCategory.DOCUMENTATION

    def test_ci_type(self):
        """GIVEN a ci conventional commit."""
        item = ChangeItem(id="7", title="ci: add lint step", raw_message="ci: add lint step")

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as INFRASTRUCTURE."""
        assert result[0].category == ChangeCategory.INFRASTRUCTURE


class TestKeywordClassification:
    """Scenarios for keyword-based classification."""

    def test_keyword_fix(self):
        """GIVEN a non-conventional message with "fix" keyword."""
        item = ChangeItem(id="k1", title="Fix broken redirect", raw_message="Fix broken redirect")

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as BUGFIX via keyword fallback."""
        assert result[0].category == ChangeCategory.BUGFIX

    def test_keyword_add(self):
        """GIVEN a message with "add" keyword."""
        item = ChangeItem(
            id="k2",
            title="Add dark mode support",
            raw_message="Add dark mode support",
        )

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as FEATURE."""
        assert result[0].category == ChangeCategory.FEATURE

    def test_keyword_security(self):
        """GIVEN a message mentioning security."""
        item = ChangeItem(
            id="k3",
            title="Patch security vulnerability in auth",
            raw_message="Patch security vulnerability in auth",
        )

        """WHEN classifying."""
        result = classify([item])

        """THEN it is classified as SECURITY."""
        assert result[0].category == ChangeCategory.SECURITY

    def test_no_keywords_stays_other(self):
        """GIVEN a vague message matching no keywords."""
        item = ChangeItem(id="k4", title="Minor tweaks", raw_message="Minor tweaks")

        """WHEN classifying."""
        result = classify([item])

        """THEN it stays as OTHER."""
        assert result[0].category == ChangeCategory.OTHER


class TestPreClassifiedItems:
    """Scenarios for pre-classified items."""

    def test_already_classified_unchanged(self):
        """GIVEN an item already classified (e.g. from structured input)."""
        item = ChangeItem(
            id="p1",
            title="Something custom",
            category=ChangeCategory.SECURITY,
            raw_message="Something custom",
        )

        """WHEN classifying."""
        result = classify([item])

        """THEN the existing category is preserved."""
        assert result[0].category == ChangeCategory.SECURITY
