"""Tests for the GitLab API integration.

Covers:
- URL encoding for refs with slashes (the root cause of false "Not found")
- Error classification (auth failure, permission denied, not found, network)
- Response caching (TTL, invalidation)
- GitLabClient methods with mocked HTTP
- GitLabInspector auth-first flow
- Web API endpoints for GitLab
- Settings integration
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from releasepilot.sources.gitlab import (
    GitLabClient,
    GitLabError,
    GitLabErrorKind,
)
from releasepilot.sources.gitlab_inspector import (
    GitLabInspector,
)

# ── Mocked API Method Tests ────────────────────────────────────────────────


def _mock_client():
    """Create a client with a mocked _request method."""
    client = GitLabClient(base_url="https://gitlab.example.com", token="test-token")
    client._request = MagicMock()
    return client


# ── Inspector Tests ─────────────────────────────────────────────────────────


def _mock_inspector():
    """Create an inspector with a mocked client."""
    client = _mock_client()
    return GitLabInspector(client), client


# ── Cache Integration Tests ────────────────────────────────────────────────


class TestInspectorAuthFlow:
    """Auth must be checked FIRST, before any data fetch."""

    """GIVEN a scenario for auth failure stops immediately"""

    def test_auth_failure_stops_immediately(self):
        """WHEN the test exercises auth failure stops immediately"""
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "Invalid token",
            kind=GitLabErrorKind.AUTH_FAILED,
        )
        result = inspector.inspect("group/repo")
        """THEN the expected behavior for auth failure stops immediately is observed"""
        assert result.is_authenticated is False
        assert result.is_accessible is False
        assert "auth_failed" in result.error_kind
        # Should only have called validate_token (1 call), not continued
        assert client._request.call_count == 1

    """GIVEN a scenario for project not found"""

    def test_project_not_found(self):
        """WHEN the test exercises project not found"""
        inspector, client = _mock_inspector()
        # validate_token succeeds
        client._request.side_effect = [
            {"username": "admin"},  # validate_token
            GitLabError("Not found", kind=GitLabErrorKind.NOT_FOUND),  # get_project
        ]
        result = inspector.inspect("nonexistent/repo")
        """THEN the expected behavior for project not found is observed"""
        assert result.is_authenticated is True
        assert result.is_accessible is False
        assert "not_found" in result.error_kind

    """GIVEN a scenario for successful inspection"""

    def test_successful_inspection(self):
        """WHEN the test exercises successful inspection"""
        inspector, client = _mock_inspector()
        client._request.side_effect = [
            {"username": "admin"},  # validate_token
            {  # get_project
                "id": 42,
                "name": "repo",
                "path_with_namespace": "group/repo",
                "default_branch": "main",
                "web_url": "https://gitlab.example.com/group/repo",
                "visibility": "internal",
                "description": "",
            },
            [  # list_branches
                {
                    "name": "main",
                    "commit": {"id": "abc123", "committed_date": "2024-01-01"},
                    "default": True,
                    "protected": True,
                },
                {
                    "name": "release/2026.04",
                    "commit": {"id": "def456", "committed_date": "2024-06-01"},
                    "default": False,
                    "protected": False,
                },
            ],
            [  # list_tags
                {
                    "name": "v1.0.0",
                    "commit": {"id": "tag123", "committed_date": "2024-01-01"},
                    "message": "Release",
                },
            ],
        ]
        result = inspector.inspect("group/repo")
        """THEN the expected behavior for successful inspection is observed"""
        assert result.is_authenticated is True
        assert result.is_accessible is True
        assert result.default_branch == "main"
        assert len(result.branches) == 2
        assert len(result.tags) == 1
        assert any(b.name == "release/2026.04" for b in result.branches)

    """GIVEN Even if branch listing fails, we still return project info"""

    def test_branch_list_failure_is_non_fatal(self):
        """WHEN the test exercises branch list failure is non fatal"""
        inspector, client = _mock_inspector()
        client._request.side_effect = [
            {"username": "admin"},
            {
                "id": 42,
                "name": "repo",
                "path_with_namespace": "group/repo",
                "default_branch": "main",
                "web_url": "",
                "visibility": "internal",
                "description": "",
            },
            GitLabError("API error", kind=GitLabErrorKind.SERVER_ERROR),  # list_branches
            [],  # list_tags
        ]
        result = inspector.inspect("group/repo")
        """THEN the expected behavior for branch list failure is non fatal is observed"""
        assert result.is_accessible is True
        assert len(result.branches) == 0
        assert any("Could not list branches" in d for d in result.diagnostics)


class TestBranchLookup:
    """Targeted branch lookup must handle all cases."""

    """GIVEN a scenario for found"""

    def test_found(self):
        """WHEN the test exercises found"""
        inspector, client = _mock_inspector()
        client._request.return_value = {
            "name": "release/2026.04",
            "commit": {"id": "abc123", "committed_date": "2024-01-01"},
            "default": False,
            "protected": False,
        }
        result = inspector.lookup_branch(42, "release/2026.04")
        """THEN the expected behavior for found is observed"""
        assert result.found is True
        assert result.branch is not None
        assert result.branch.name == "release/2026.04"

    """GIVEN a scenario for not found"""

    def test_not_found(self):
        """WHEN the test exercises not found"""
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "Not found",
            kind=GitLabErrorKind.NOT_FOUND,
        )
        result = inspector.lookup_branch(42, "nonexistent/branch")
        """THEN the expected behavior for not found is observed"""
        assert result.found is False
        assert "not_found" in result.error_kind
        assert "does not exist" in result.error

    """GIVEN a scenario for auth failure on lookup"""

    def test_auth_failure_on_lookup(self):
        """WHEN the test exercises auth failure on lookup"""
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "401",
            kind=GitLabErrorKind.AUTH_FAILED,
        )
        result = inspector.lookup_branch(42, "main")
        """THEN the expected behavior for auth failure on lookup is observed"""
        assert result.found is False
        assert "auth_failed" in result.error_kind


class TestTagLookup:
    """GIVEN a scenario for found"""

    def test_found(self):
        """WHEN the test exercises found"""
        inspector, client = _mock_inspector()
        client._request.return_value = {
            "name": "v1.0.0",
            "commit": {"id": "abc123", "committed_date": "2024-01-01"},
            "message": "Release",
        }
        result = inspector.lookup_tag(42, "v1.0.0")
        """THEN the expected behavior for found is observed"""
        assert result.found is True
        assert result.tag.name == "v1.0.0"

    """GIVEN a scenario for not found"""

    def test_not_found(self):
        """WHEN the test exercises not found"""
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "Not found",
            kind=GitLabErrorKind.NOT_FOUND,
        )
        result = inspector.lookup_tag(42, "nonexistent")
        """THEN the expected behavior for not found is observed"""
        assert result.found is False


class TestCheckExists:
    """GIVEN a scenario for branch exists"""

    def test_branch_exists(self):
        """WHEN the test exercises branch exists"""
        inspector, client = _mock_inspector()
        client._request.return_value = {
            "name": "release/2026.04",
            "commit": {"id": "abc123"},
            "default": False,
            "protected": False,
        }
        """THEN the expected behavior for branch exists is observed"""
        assert inspector.check_branch_exists(42, "release/2026.04") is True

    """GIVEN a scenario for branch not exists"""

    def test_branch_not_exists(self):
        """WHEN the test exercises branch not exists"""
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "Not found",
            kind=GitLabErrorKind.NOT_FOUND,
        )
        """THEN the expected behavior for branch not exists is observed"""
        assert inspector.check_branch_exists(42, "nope") is False


class TestInspectorConstruction:
    """GIVEN a scenario for from config"""

    def test_from_config(self):
        """WHEN the test exercises from config"""
        inspector = GitLabInspector.from_config(
            gitlab_url="https://gitlab.example.com",
            gitlab_token="glpat-test",
        )
        """THEN the expected behavior for from config is observed"""
        assert inspector._client._base_url == "https://gitlab.example.com"
        assert inspector._client._token == "glpat-test"

    """GIVEN a scenario for from env missing url"""

    def test_from_env_missing_url(self):
        """WHEN the test exercises from env missing url"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(GitLabError) as exc_info:
                GitLabInspector.from_env()
            assert "RELEASEPILOT_GITLAB_URL" in str(exc_info.value)

    """GIVEN a scenario for from env with values"""

    def test_from_env_with_values(self):
        """WHEN the test exercises from env with values"""
        env = {
            "RELEASEPILOT_GITLAB_URL": "https://gitlab.example.com",
            "RELEASEPILOT_GITLAB_TOKEN": "glpat-test",
        }
        with patch.dict("os.environ", env, clear=True):
            inspector = GitLabInspector.from_env()
            assert inspector._client._base_url == "https://gitlab.example.com"

    """GIVEN a scenario for from env ssl verify disabled"""

    def test_from_env_ssl_verify_disabled(self):
        """WHEN the test exercises from env ssl verify disabled"""
        env = {
            "RELEASEPILOT_GITLAB_URL": "https://gitlab.example.com",
            "RELEASEPILOT_GITLAB_TOKEN": "glpat-test",
            "RELEASEPILOT_GITLAB_SSL_VERIFY": "false",
        }
        with patch.dict("os.environ", env, clear=True):
            inspector = GitLabInspector.from_env()
            assert inspector._client._verify_ssl is False
