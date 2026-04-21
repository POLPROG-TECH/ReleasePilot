"""Tests for deduplication."""

from __future__ import annotations

from releasepilot.domain.models import ChangeItem, SourceReference
from releasepilot.processing.dedup import deduplicate


class TestExactDedup:
    """Scenarios for exact deduplication."""

    """GIVEN two items with the same commit hash"""

    def test_duplicate_commit_hashes_removed(self):
        items = [
            ChangeItem(
                id="d1",
                title="Fix login",
                source=SourceReference(commit_hash="aaa111"),
                raw_message="fix: login",
            ),
            ChangeItem(
                id="d2",
                title="Fix login",
                source=SourceReference(commit_hash="aaa111"),
                raw_message="fix: login",
            ),
        ]

        """WHEN deduplicating"""
        result = deduplicate(items)

        """THEN only one remains"""
        assert len(result) == 1

    """GIVEN two items with different hashes"""

    def test_different_hashes_preserved(self):
        items = [
            ChangeItem(
                id="d3",
                title="Fix A",
                source=SourceReference(commit_hash="aaa"),
                raw_message="a",
            ),
            ChangeItem(
                id="d4",
                title="Fix B",
                source=SourceReference(commit_hash="bbb"),
                raw_message="b",
            ),
        ]

        """WHEN deduplicating"""
        result = deduplicate(items)

        """THEN both are preserved"""
        assert len(result) == 2


class TestPRGrouping:
    """Scenarios for PR-based grouping."""

    """GIVEN three commits all linked to PR #42"""

    def test_multiple_commits_same_pr_merged(self):
        items = [
            ChangeItem(
                id="p1",
                title="WIP on feature",
                source=SourceReference(commit_hash="a1", pr_number=42),
                raw_message="WIP on feature",
            ),
            ChangeItem(
                id="p2",
                title="Continue feature",
                description="Detailed work on the feature",
                source=SourceReference(commit_hash="a2", pr_number=42),
                raw_message="Continue feature",
            ),
            ChangeItem(
                id="p3",
                title="Finalize feature",
                source=SourceReference(commit_hash="a3", pr_number=42),
                raw_message="Finalize feature",
            ),
        ]

        """WHEN deduplicating"""
        result = deduplicate(items)

        """THEN only one item remains (the most informative)"""
        assert len(result) == 1
        assert result[0].description == "Detailed work on the feature"

    """GIVEN commits from different PRs"""

    def test_different_prs_preserved(self):
        items = [
            ChangeItem(
                id="q1",
                title="Feature A",
                source=SourceReference(commit_hash="x1", pr_number=10),
                raw_message="a",
            ),
            ChangeItem(
                id="q2",
                title="Feature B",
                source=SourceReference(commit_hash="x2", pr_number=20),
                raw_message="b",
            ),
        ]

        """WHEN deduplicating"""
        result = deduplicate(items)

        """THEN both are preserved"""
        assert len(result) == 2


class TestNearDuplicateDetection:
    """Scenarios for near-duplicate detection."""

    """GIVEN two items with nearly identical titles"""

    def test_near_duplicate_titles_removed(self):
        items = [
            ChangeItem(
                id="n1",
                title="Fix the broken login redirect issue",
                source=SourceReference(commit_hash="h1"),
                raw_message="Fix the broken login redirect issue",
            ),
            ChangeItem(
                id="n2",
                title="Fix the broken login redirect problem",
                source=SourceReference(commit_hash="h2"),
                raw_message="Fix the broken login redirect problem",
            ),
        ]

        """WHEN deduplicating"""
        result = deduplicate(items)

        """THEN only one remains"""
        assert len(result) == 1

    """GIVEN two items with completely different titles"""

    def test_distinct_titles_preserved(self):
        items = [
            ChangeItem(
                id="d1",
                title="Add dark mode support for dashboard",
                source=SourceReference(commit_hash="h3"),
                raw_message="Add dark mode support for dashboard",
            ),
            ChangeItem(
                id="d2",
                title="Fix authentication timeout errors",
                source=SourceReference(commit_hash="h4"),
                raw_message="Fix authentication timeout errors",
            ),
        ]

        """WHEN deduplicating"""
        result = deduplicate(items)

        """THEN both are preserved"""
        assert len(result) == 2
