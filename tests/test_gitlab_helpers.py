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

import time
from unittest.mock import MagicMock, patch

import pytest

from releasepilot.sources.gitlab import (
    GitLabBranch,
    GitLabClient,
    GitLabCommit,
    GitLabError,
    GitLabErrorKind,
    GitLabProject,
    GitLabTag,
    _ResponseCache,
    encode_project_path,
    encode_ref,
)
from releasepilot.sources.gitlab_inspector import (
    BranchLookupResult,
    GitLabInspector,
    GitLabRepoInspection,
    TagLookupResult,
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


# ── Inspector from_env/from_config Tests ────────────────────────────────────


class TestEncodeRef:
    """Branch names with slashes MUST be encoded for GitLab API."""

    """GIVEN a scenario for simple branch"""

    def test_simple_branch(self):
        """WHEN the test exercises simple branch"""
        """THEN the expected behavior for simple branch is observed"""
        assert encode_ref("main") == "main"

    """GIVEN The core bug: release/2026.04 was NOT being encoded"""

    def test_branch_with_slash(self):
        """WHEN the test exercises branch with slash"""
        """THEN the expected behavior for branch with slash is observed"""
        assert encode_ref("release/2026.04") == "release%2F2026.04"

    """GIVEN a scenario for branch with multiple slashes"""

    def test_branch_with_multiple_slashes(self):
        """WHEN the test exercises branch with multiple slashes"""
        """THEN the expected behavior for branch with multiple slashes is observed"""
        assert encode_ref("feature/JIRA-123/my-feature") == "feature%2FJIRA-123%2Fmy-feature"

    """GIVEN a scenario for branch with dots"""

    def test_branch_with_dots(self):
        """WHEN the test exercises branch with dots"""
        """THEN the expected behavior for branch with dots is observed"""
        assert encode_ref("v1.2.3") == "v1.2.3"

    """GIVEN a scenario for branch with special chars"""

    def test_branch_with_special_chars(self):
        """WHEN the test exercises branch with special chars"""
        result = encode_ref("release/2026.04-RC1")
        """THEN the expected behavior for branch with special chars is observed"""
        assert "%2F" in result
        assert "2026.04-RC1" in result

    """GIVEN a scenario for empty ref"""

    def test_empty_ref(self):
        """WHEN the test exercises empty ref"""
        """THEN the expected behavior for empty ref is observed"""
        assert encode_ref("") == ""

    """GIVEN a scenario for branch with hash"""

    def test_branch_with_hash(self):
        """WHEN the test exercises branch with hash"""
        result = encode_ref("fix/#123")
        """THEN the expected behavior for branch with hash is observed"""
        assert "%2F" in result
        assert "%23" in result

    """GIVEN a scenario for branch with spaces"""

    def test_branch_with_spaces(self):
        """WHEN the test exercises branch with spaces"""
        result = encode_ref("my branch")
        """THEN the expected behavior for branch with spaces is observed"""
        assert "%20" in result


class TestEncodeProjectPath:
    """Project paths with slashes need encoding for API path segments."""

    """GIVEN a scenario for simple path"""

    def test_simple_path(self):
        """WHEN the test exercises simple path"""
        """THEN the expected behavior for simple path is observed"""
        assert encode_project_path("myproject") == "myproject"

    """GIVEN a scenario for group project"""

    def test_group_project(self):
        """WHEN the test exercises group project"""
        """THEN the expected behavior for group project is observed"""
        assert encode_project_path("group/repo") == "group%2Frepo"

    """GIVEN The exact path from the user's bug report"""

    def test_deep_nested_path(self):
        """WHEN the test exercises deep nested path"""
        path = "EMEA/GAD/MerchantPortal/UI/experience-domain/additional-reports"
        encoded = encode_project_path(path)
        """THEN the expected behavior for deep nested path is observed"""
        assert "%2F" in encoded
        assert "/" not in encoded  # All slashes must be encoded


class TestResponseCache:
    """Verify caching eliminates redundant API calls."""

    """GIVEN a scenario for cache hit"""

    def test_cache_hit(self):
        """WHEN the test exercises cache hit"""
        cache = _ResponseCache(default_ttl=60.0)
        cache.put("key1", {"data": "value"})
        """THEN the expected behavior for cache hit is observed"""
        assert cache.get("key1") == {"data": "value"}

    """GIVEN a scenario for cache miss"""

    def test_cache_miss(self):
        """WHEN the test exercises cache miss"""
        cache = _ResponseCache(default_ttl=60.0)
        """THEN the expected behavior for cache miss is observed"""
        assert cache.get("nonexistent") is None

    """GIVEN a scenario for cache expiry"""

    def test_cache_expiry(self):
        """WHEN the test exercises cache expiry"""
        cache = _ResponseCache(default_ttl=0.01)
        cache.put("key1", "value")
        time.sleep(0.02)
        """THEN the expected behavior for cache expiry is observed"""
        assert cache.get("key1") is None

    """GIVEN a scenario for cache invalidate all"""

    def test_cache_invalidate_all(self):
        """WHEN the test exercises cache invalidate all"""
        cache = _ResponseCache()
        cache.put("a", 1)
        cache.put("b", 2)
        cache.invalidate()
        """THEN the expected behavior for cache invalidate all is observed"""
        assert cache.get("a") is None
        assert cache.get("b") is None

    """GIVEN a scenario for cache invalidate prefix"""

    def test_cache_invalidate_prefix(self):
        """WHEN the test exercises cache invalidate prefix"""
        cache = _ResponseCache()
        cache.put("project/1/branches", "data1")
        cache.put("project/1/tags", "data2")
        cache.put("project/2/branches", "data3")
        cache.invalidate("project/1")
        """THEN the expected behavior for cache invalidate prefix is observed"""
        assert cache.get("project/1/branches") is None
        assert cache.get("project/1/tags") is None
        assert cache.get("project/2/branches") == "data3"

    """GIVEN a scenario for cache custom ttl"""

    def test_cache_custom_ttl(self):
        """WHEN the test exercises cache custom ttl"""
        cache = _ResponseCache(default_ttl=60.0)
        cache.put("short", "val", ttl=0.01)
        cache.put("long", "val", ttl=60.0)
        time.sleep(0.02)
        """THEN the expected behavior for cache custom ttl is observed"""
        assert cache.get("short") is None
        assert cache.get("long") == "val"


class TestGitLabError:
    """Error types must be clearly distinguishable."""

    """GIVEN a scenario for auth error is auth"""

    def test_auth_error_is_auth(self):
        """WHEN the test exercises auth error is auth"""
        err = GitLabError("bad token", kind=GitLabErrorKind.AUTH_FAILED)
        """THEN the expected behavior for auth error is auth is observed"""
        assert err.is_auth_error is True
        assert err.is_retriable is False

    """GIVEN a scenario for permission error is auth"""

    def test_permission_error_is_auth(self):
        """WHEN the test exercises permission error is auth"""
        err = GitLabError("no access", kind=GitLabErrorKind.PERMISSION_DENIED)
        """THEN the expected behavior for permission error is auth is observed"""
        assert err.is_auth_error is True

    """GIVEN a scenario for not found is not auth"""

    def test_not_found_is_not_auth(self):
        """WHEN the test exercises not found is not auth"""
        err = GitLabError("missing", kind=GitLabErrorKind.NOT_FOUND)
        """THEN the expected behavior for not found is not auth is observed"""
        assert err.is_auth_error is False
        assert err.is_retriable is False

    """GIVEN a scenario for network error is retriable"""

    def test_network_error_is_retriable(self):
        """WHEN the test exercises network error is retriable"""
        err = GitLabError("timeout", kind=GitLabErrorKind.NETWORK_ERROR)
        """THEN the expected behavior for network error is retriable is observed"""
        assert err.is_retriable is True

    """GIVEN a scenario for timeout is retriable"""

    def test_timeout_is_retriable(self):
        """WHEN the test exercises timeout is retriable"""
        err = GitLabError("timeout", kind=GitLabErrorKind.TIMEOUT)
        """THEN the expected behavior for timeout is retriable is observed"""
        assert err.is_retriable is True

    """GIVEN a scenario for rate limited is retriable"""

    def test_rate_limited_is_retriable(self):
        """WHEN the test exercises rate limited is retriable"""
        err = GitLabError("429", kind=GitLabErrorKind.RATE_LIMITED)
        """THEN the expected behavior for rate limited is retriable is observed"""
        assert err.is_retriable is True

    """GIVEN a scenario for server error is retriable"""

    def test_server_error_is_retriable(self):
        """WHEN the test exercises server error is retriable"""
        err = GitLabError("500", kind=GitLabErrorKind.SERVER_ERROR)
        """THEN the expected behavior for server error is retriable is observed"""
        assert err.is_retriable is True

    """GIVEN a scenario for str includes kind"""

    def test_str_includes_kind(self):
        """WHEN the test exercises str includes kind"""
        err = GitLabError("bad token", kind=GitLabErrorKind.AUTH_FAILED)
        """THEN the expected behavior for str includes kind is observed"""
        assert "[auth_failed]" in str(err)


class TestErrorClassification:
    """Client._classify_http_error maps HTTP status to error kinds."""

    def setup_method(self):
        with patch.object(GitLabClient, "__init__", lambda self, **kw: None):
            self.client = GitLabClient()
        self.client._base_url = "https://gitlab.example.com"

    """GIVEN a scenario for 401 maps to auth failed"""

    def test_401_maps_to_auth_failed(self):
        """WHEN the test exercises 401 maps to auth failed"""
        err = self.client._classify_http_error(401, "Unauthorized", "/test")
        """THEN the expected behavior for 401 maps to auth failed is observed"""
        assert err.kind == GitLabErrorKind.AUTH_FAILED
        assert err.status_code == 401

    """GIVEN a scenario for 403 maps to permission denied"""

    def test_403_maps_to_permission_denied(self):
        """WHEN the test exercises 403 maps to permission denied"""
        err = self.client._classify_http_error(403, "Forbidden", "/test")
        """THEN the expected behavior for 403 maps to permission denied is observed"""
        assert err.kind == GitLabErrorKind.PERMISSION_DENIED
        assert err.status_code == 403

    """GIVEN a scenario for 404 maps to not found"""

    def test_404_maps_to_not_found(self):
        """WHEN the test exercises 404 maps to not found"""
        err = self.client._classify_http_error(404, "Not Found", "/test")
        """THEN the expected behavior for 404 maps to not found is observed"""
        assert err.kind == GitLabErrorKind.NOT_FOUND
        assert err.status_code == 404

    """GIVEN a scenario for 429 maps to rate limited"""

    def test_429_maps_to_rate_limited(self):
        """WHEN the test exercises 429 maps to rate limited"""
        err = self.client._classify_http_error(429, "Too Many", "/test")
        """THEN the expected behavior for 429 maps to rate limited is observed"""
        assert err.kind == GitLabErrorKind.RATE_LIMITED

    """GIVEN a scenario for 500 maps to server error"""

    def test_500_maps_to_server_error(self):
        """WHEN the test exercises 500 maps to server error"""
        err = self.client._classify_http_error(500, "ISE", "/test")
        """THEN the expected behavior for 500 maps to server error is observed"""
        assert err.kind == GitLabErrorKind.SERVER_ERROR

    """GIVEN a scenario for 502 maps to server error"""

    def test_502_maps_to_server_error(self):
        """WHEN the test exercises 502 maps to server error"""
        err = self.client._classify_http_error(502, "Bad Gateway", "/test")
        """THEN the expected behavior for 502 maps to server error is observed"""
        assert err.kind == GitLabErrorKind.SERVER_ERROR

    """GIVEN a scenario for unknown status"""

    def test_unknown_status(self):
        """WHEN the test exercises unknown status"""
        err = self.client._classify_http_error(418, "Teapot", "/test")
        """THEN the expected behavior for unknown status is observed"""
        assert err.kind == GitLabErrorKind.INVALID_RESPONSE


class TestDataModels:
    """Frozen dataclasses must be hashable and comparable."""

    """GIVEN a scenario for branch frozen"""

    def test_branch_frozen(self):
        """WHEN the test exercises branch frozen"""
        b = GitLabBranch(name="main", commit_sha="abc")
        """THEN the expected behavior for branch frozen is observed"""
        with pytest.raises(AttributeError):
            b.name = "other"  # type: ignore[misc]

    """GIVEN a scenario for tag frozen"""

    def test_tag_frozen(self):
        """WHEN the test exercises tag frozen"""
        t = GitLabTag(name="v1.0", commit_sha="abc")
        """THEN the expected behavior for tag frozen is observed"""
        with pytest.raises(AttributeError):
            t.name = "other"  # type: ignore[misc]

    """GIVEN a scenario for project frozen"""

    def test_project_frozen(self):
        """WHEN the test exercises project frozen"""
        p = GitLabProject(id=1, name="test", path_with_namespace="g/t")
        """THEN the expected behavior for project frozen is observed"""
        with pytest.raises(AttributeError):
            p.id = 2  # type: ignore[misc]

    """GIVEN a scenario for commit frozen"""

    def test_commit_frozen(self):
        """WHEN the test exercises commit frozen"""
        c = GitLabCommit(
            sha="abc",
            short_id="abc",
            title="t",
            message="m",
            author_name="a",
            authored_date="d",
            committed_date="d",
        )
        """THEN the expected behavior for commit frozen is observed"""
        with pytest.raises(AttributeError):
            c.sha = "other"  # type: ignore[misc]

    """GIVEN a scenario for inspection defaults"""

    def test_inspection_defaults(self):
        """WHEN the test exercises inspection defaults"""
        r = GitLabRepoInspection()
        """THEN the expected behavior for inspection defaults is observed"""
        assert r.project is None
        assert r.branches == ()
        assert r.tags == ()
        assert r.is_accessible is False

    """GIVEN a scenario for branch lookup result defaults"""

    def test_branch_lookup_result_defaults(self):
        """WHEN the test exercises branch lookup result defaults"""
        r = BranchLookupResult()
        """THEN the expected behavior for branch lookup result defaults is observed"""
        assert r.found is False
        assert r.branch is None

    """GIVEN a scenario for tag lookup result defaults"""

    def test_tag_lookup_result_defaults(self):
        """WHEN the test exercises tag lookup result defaults"""
        r = TagLookupResult()
        """THEN the expected behavior for tag lookup result defaults is observed"""
        assert r.found is False
        assert r.tag is None
