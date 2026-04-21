"""Tests for the classification engine."""

from __future__ import annotations

from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import ChangeItem
from releasepilot.processing.classifier import classify


class TestConventionalCommitParsing:
    """Scenarios for conventional commit parsing."""

    """GIVEN a conventional commit with feat type"""

    def test_feat_type(self):
        item = ChangeItem(id="1", title="feat: add login page", raw_message="feat: add login page")

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as FEATURE"""
        assert result[0].category == ChangeCategory.FEATURE
        assert result[0].title == "add login page"

    """GIVEN a conventional commit with fix type and scope"""

    def test_fix_type_with_scope(self):
        item = ChangeItem(
            id="2",
            title="fix(auth): resolve token expiry",
            raw_message="fix(auth): resolve token expiry",
        )

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as BUGFIX with correct scope"""
        assert result[0].category == ChangeCategory.BUGFIX
        assert result[0].scope == "auth"
        assert result[0].title == "resolve token expiry"

    """GIVEN a conventional commit with breaking change indicator"""

    def test_breaking_change_with_bang(self):
        item = ChangeItem(
            id="3",
            title="feat(api)!: remove v1 endpoints",
            raw_message="feat(api)!: remove v1 endpoints",
        )

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as BREAKING with high importance"""
        assert result[0].category == ChangeCategory.BREAKING
        assert result[0].is_breaking is True
        assert result[0].importance == Importance.HIGH

    """GIVEN a commit with BREAKING CHANGE in the body"""

    def test_breaking_change_footer(self):
        item = ChangeItem(
            id="4",
            title="feat: new auth flow",
            raw_message="feat: new auth flow\n\nBREAKING CHANGE: old tokens invalidated",
        )

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as BREAKING"""
        assert result[0].category == ChangeCategory.BREAKING
        assert result[0].is_breaking is True

    """GIVEN a perf conventional commit"""

    def test_perf_type(self):
        item = ChangeItem(id="5", title="perf: optimize query", raw_message="perf: optimize query")

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as PERFORMANCE"""
        assert result[0].category == ChangeCategory.PERFORMANCE

    """GIVEN a docs conventional commit"""

    def test_docs_type(self):
        item = ChangeItem(id="6", title="docs: update README", raw_message="docs: update README")

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as DOCUMENTATION"""
        assert result[0].category == ChangeCategory.DOCUMENTATION

    """GIVEN a ci conventional commit"""

    def test_ci_type(self):
        item = ChangeItem(id="7", title="ci: add lint step", raw_message="ci: add lint step")

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as INFRASTRUCTURE"""
        assert result[0].category == ChangeCategory.INFRASTRUCTURE


class TestKeywordClassification:
    """Scenarios for keyword-based classification."""

    """GIVEN a non-conventional message with "fix" keyword"""

    def test_keyword_fix(self):
        item = ChangeItem(id="k1", title="Fix broken redirect", raw_message="Fix broken redirect")

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as BUGFIX via keyword fallback"""
        assert result[0].category == ChangeCategory.BUGFIX

    """GIVEN a message with "add" keyword"""

    def test_keyword_add(self):
        item = ChangeItem(
            id="k2",
            title="Add dark mode support",
            raw_message="Add dark mode support",
        )

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as FEATURE"""
        assert result[0].category == ChangeCategory.FEATURE

    """GIVEN a message mentioning security"""

    def test_keyword_security(self):
        item = ChangeItem(
            id="k3",
            title="Patch security vulnerability in auth",
            raw_message="Patch security vulnerability in auth",
        )

        """WHEN classifying"""
        result = classify([item])

        """THEN it is classified as SECURITY"""
        assert result[0].category == ChangeCategory.SECURITY

    """GIVEN a vague message matching no keywords"""

    def test_no_keywords_stays_other(self):
        item = ChangeItem(id="k4", title="Minor tweaks", raw_message="Minor tweaks")

        """WHEN classifying"""
        result = classify([item])

        """THEN it stays as OTHER"""
        assert result[0].category == ChangeCategory.OTHER


class TestPreClassifiedItems:
    """Scenarios for pre-classified items."""

    """GIVEN an item already classified (e.g. from structured input)"""

    def test_already_classified_unchanged(self):
        item = ChangeItem(
            id="p1",
            title="Something custom",
            category=ChangeCategory.SECURITY,
            raw_message="Something custom",
        )

        """WHEN classifying"""
        result = classify([item])

        """THEN the existing category is preserved"""
        assert result[0].category == ChangeCategory.SECURITY
