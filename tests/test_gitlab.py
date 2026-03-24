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

import json
import ssl
import time
import urllib.error
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

# ── URL Encoding Tests ─────────────────────────────────────────────────────


class TestEncodeRef:
    """Branch names with slashes MUST be encoded for GitLab API."""

    def test_simple_branch(self):
        assert encode_ref("main") == "main"

    def test_branch_with_slash(self):
        """The core bug: release/2026.04 was NOT being encoded."""
        assert encode_ref("release/2026.04") == "release%2F2026.04"

    def test_branch_with_multiple_slashes(self):
        assert encode_ref("feature/JIRA-123/my-feature") == "feature%2FJIRA-123%2Fmy-feature"

    def test_branch_with_dots(self):
        assert encode_ref("v1.2.3") == "v1.2.3"

    def test_branch_with_special_chars(self):
        result = encode_ref("release/2026.04-RC1")
        assert "%2F" in result
        assert "2026.04-RC1" in result

    def test_empty_ref(self):
        assert encode_ref("") == ""

    def test_branch_with_hash(self):
        result = encode_ref("fix/#123")
        assert "%2F" in result
        assert "%23" in result

    def test_branch_with_spaces(self):
        result = encode_ref("my branch")
        assert "%20" in result


class TestEncodeProjectPath:
    """Project paths with slashes need encoding for API path segments."""

    def test_simple_path(self):
        assert encode_project_path("myproject") == "myproject"

    def test_group_project(self):
        assert encode_project_path("group/repo") == "group%2Frepo"

    def test_deep_nested_path(self):
        """The exact path from the user's bug report."""
        path = "EMEA/GAD/MerchantPortal/UI/experience-domain/additional-reports"
        encoded = encode_project_path(path)
        assert "%2F" in encoded
        assert "/" not in encoded  # All slashes must be encoded


# ── Cache Tests ─────────────────────────────────────────────────────────────


class TestResponseCache:
    """Verify caching eliminates redundant API calls."""

    def test_cache_hit(self):
        cache = _ResponseCache(default_ttl=60.0)
        cache.put("key1", {"data": "value"})
        assert cache.get("key1") == {"data": "value"}

    def test_cache_miss(self):
        cache = _ResponseCache(default_ttl=60.0)
        assert cache.get("nonexistent") is None

    def test_cache_expiry(self):
        cache = _ResponseCache(default_ttl=0.01)
        cache.put("key1", "value")
        time.sleep(0.02)
        assert cache.get("key1") is None

    def test_cache_invalidate_all(self):
        cache = _ResponseCache()
        cache.put("a", 1)
        cache.put("b", 2)
        cache.invalidate()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_cache_invalidate_prefix(self):
        cache = _ResponseCache()
        cache.put("project/1/branches", "data1")
        cache.put("project/1/tags", "data2")
        cache.put("project/2/branches", "data3")
        cache.invalidate("project/1")
        assert cache.get("project/1/branches") is None
        assert cache.get("project/1/tags") is None
        assert cache.get("project/2/branches") == "data3"

    def test_cache_custom_ttl(self):
        cache = _ResponseCache(default_ttl=60.0)
        cache.put("short", "val", ttl=0.01)
        cache.put("long", "val", ttl=60.0)
        time.sleep(0.02)
        assert cache.get("short") is None
        assert cache.get("long") == "val"


# ── Error Classification Tests ──────────────────────────────────────────────


class TestGitLabError:
    """Error types must be clearly distinguishable."""

    def test_auth_error_is_auth(self):
        err = GitLabError("bad token", kind=GitLabErrorKind.AUTH_FAILED)
        assert err.is_auth_error is True
        assert err.is_retriable is False

    def test_permission_error_is_auth(self):
        err = GitLabError("no access", kind=GitLabErrorKind.PERMISSION_DENIED)
        assert err.is_auth_error is True

    def test_not_found_is_not_auth(self):
        err = GitLabError("missing", kind=GitLabErrorKind.NOT_FOUND)
        assert err.is_auth_error is False
        assert err.is_retriable is False

    def test_network_error_is_retriable(self):
        err = GitLabError("timeout", kind=GitLabErrorKind.NETWORK_ERROR)
        assert err.is_retriable is True

    def test_timeout_is_retriable(self):
        err = GitLabError("timeout", kind=GitLabErrorKind.TIMEOUT)
        assert err.is_retriable is True

    def test_rate_limited_is_retriable(self):
        err = GitLabError("429", kind=GitLabErrorKind.RATE_LIMITED)
        assert err.is_retriable is True

    def test_server_error_is_retriable(self):
        err = GitLabError("500", kind=GitLabErrorKind.SERVER_ERROR)
        assert err.is_retriable is True

    def test_str_includes_kind(self):
        err = GitLabError("bad token", kind=GitLabErrorKind.AUTH_FAILED)
        assert "[auth_failed]" in str(err)


class TestErrorClassification:
    """Client._classify_http_error maps HTTP status to error kinds."""

    def setup_method(self):
        with patch.object(GitLabClient, "__init__", lambda self, **kw: None):
            self.client = GitLabClient()
        self.client._base_url = "https://gitlab.example.com"

    def test_401_maps_to_auth_failed(self):
        err = self.client._classify_http_error(401, "Unauthorized", "/test")
        assert err.kind == GitLabErrorKind.AUTH_FAILED
        assert err.status_code == 401

    def test_403_maps_to_permission_denied(self):
        err = self.client._classify_http_error(403, "Forbidden", "/test")
        assert err.kind == GitLabErrorKind.PERMISSION_DENIED
        assert err.status_code == 403

    def test_404_maps_to_not_found(self):
        err = self.client._classify_http_error(404, "Not Found", "/test")
        assert err.kind == GitLabErrorKind.NOT_FOUND
        assert err.status_code == 404

    def test_429_maps_to_rate_limited(self):
        err = self.client._classify_http_error(429, "Too Many", "/test")
        assert err.kind == GitLabErrorKind.RATE_LIMITED

    def test_500_maps_to_server_error(self):
        err = self.client._classify_http_error(500, "ISE", "/test")
        assert err.kind == GitLabErrorKind.SERVER_ERROR

    def test_502_maps_to_server_error(self):
        err = self.client._classify_http_error(502, "Bad Gateway", "/test")
        assert err.kind == GitLabErrorKind.SERVER_ERROR

    def test_unknown_status(self):
        err = self.client._classify_http_error(418, "Teapot", "/test")
        assert err.kind == GitLabErrorKind.INVALID_RESPONSE


# ── Client Construction Tests ───────────────────────────────────────────────


class TestClientConstruction:
    """Token must be required — no unauthenticated clients."""

    def test_no_token_raises(self):
        with pytest.raises(GitLabError) as exc_info:
            GitLabClient(base_url="https://gitlab.example.com", token="")
        assert exc_info.value.kind == GitLabErrorKind.AUTH_FAILED

    def test_valid_construction(self):
        client = GitLabClient(
            base_url="https://gitlab.example.com",
            token="glpat-test-token",
        )
        assert client._base_url == "https://gitlab.example.com"
        assert client._token == "glpat-test-token"

    def test_trailing_slash_stripped(self):
        client = GitLabClient(
            base_url="https://gitlab.example.com/",
            token="tok",
        )
        assert client._base_url == "https://gitlab.example.com"


# ── Mocked API Method Tests ────────────────────────────────────────────────


def _mock_client():
    """Create a client with a mocked _request method."""
    client = GitLabClient(base_url="https://gitlab.example.com", token="test-token")
    client._request = MagicMock()
    return client


class TestValidateToken:
    def test_returns_user_info(self):
        client = _mock_client()
        client._request.return_value = {"username": "admin", "name": "Admin User"}
        result = client.validate_token()
        assert result["username"] == "admin"
        client._request.assert_called_once_with("GET", "/user", use_cache=False)


class TestGetProject:
    def test_by_path(self):
        client = _mock_client()
        client._request.return_value = {
            "id": 42,
            "name": "additional-reports",
            "path_with_namespace": "EMEA/GAD/MerchantPortal/UI/additional-reports",
            "default_branch": "main",
            "web_url": "https://gitlab.example.com/EMEA/GAD/MerchantPortal/UI/additional-reports",
            "visibility": "internal",
            "description": "Test project",
        }
        project = client.get_project("EMEA/GAD/MerchantPortal/UI/additional-reports")
        assert project.id == 42
        assert project.path_with_namespace == "EMEA/GAD/MerchantPortal/UI/additional-reports"
        assert project.default_branch == "main"
        assert project.visibility == "internal"

        # Verify the path was encoded
        call_args = client._request.call_args
        assert "EMEA%2FGAD%2FMerchantPortal%2FUI%2Fadditional-reports" in call_args[0][1]

    def test_by_id(self):
        client = _mock_client()
        client._request.return_value = {"id": 42, "name": "repo", "path_with_namespace": "g/r"}
        project = client.get_project(42)
        assert project.id == 42
        call_args = client._request.call_args
        assert "/projects/42" in call_args[0][1]


class TestListBranches:
    def test_returns_branches(self):
        client = _mock_client()
        client._request.return_value = [
            {
                "name": "main",
                "commit": {"id": "abc123def456", "committed_date": "2024-01-01T00:00:00Z"},
                "default": True,
                "protected": True,
            },
            {
                "name": "release/2026.04",
                "commit": {"id": "def789abc012", "committed_date": "2024-06-01T00:00:00Z"},
                "default": False,
                "protected": False,
            },
        ]
        branches = client.list_branches(42)
        assert len(branches) == 2
        assert branches[0].name == "main"
        assert branches[0].is_default is True
        assert branches[1].name == "release/2026.04"

    def test_empty_list(self):
        client = _mock_client()
        client._request.return_value = []
        branches = client.list_branches(42)
        assert branches == []

    def test_none_response(self):
        client = _mock_client()
        client._request.return_value = None
        branches = client.list_branches(42)
        assert branches == []


class TestGetBranch:
    def test_branch_with_slash(self):
        """Core regression: release/2026.04 must be found, not 404'd."""
        client = _mock_client()
        client._request.return_value = {
            "name": "release/2026.04",
            "commit": {"id": "abc123", "committed_date": "2024-01-01T00:00:00Z"},
            "default": False,
            "protected": True,
        }
        branch = client.get_branch(42, "release/2026.04")
        assert branch.name == "release/2026.04"
        assert branch.commit_sha == "abc123"

        # Verify encoding in the API path
        call_args = client._request.call_args
        api_path = call_args[0][1]
        assert "release%2F2026.04" in api_path
        assert "release/2026.04" not in api_path  # Must NOT have raw slash

    def test_simple_branch(self):
        client = _mock_client()
        client._request.return_value = {
            "name": "main",
            "commit": {"id": "abc123", "committed_date": "2024-01-01T00:00:00Z"},
            "default": True,
            "protected": True,
        }
        branch = client.get_branch(42, "main")
        assert branch.name == "main"
        assert branch.is_default is True


class TestGetTag:
    def test_simple_tag(self):
        client = _mock_client()
        client._request.return_value = {
            "name": "v1.0.0",
            "commit": {"id": "abc123", "committed_date": "2024-01-01T00:00:00Z"},
            "message": "Release 1.0",
        }
        tag = client.get_tag(42, "v1.0.0")
        assert tag.name == "v1.0.0"
        assert tag.message == "Release 1.0"

    def test_tag_with_slash(self):
        client = _mock_client()
        client._request.return_value = {
            "name": "release/v1.0",
            "commit": {"id": "def456"},
        }
        _ = client.get_tag(42, "release/v1.0")
        # Verify encoding
        call_args = client._request.call_args
        assert "release%2Fv1.0" in call_args[0][1]


class TestListCommits:
    def test_returns_commits(self):
        client = _mock_client()
        client._request.return_value = [
            {
                "id": "abc123",
                "short_id": "abc123",
                "title": "feat: add feature",
                "message": "feat: add feature\n\nDetails here.",
                "author_name": "Dev",
                "authored_date": "2024-01-01T00:00:00Z",
                "committed_date": "2024-01-01T00:00:00Z",
            },
        ]
        commits = client.list_commits(42, ref="main")
        assert len(commits) == 1
        assert commits[0].title == "feat: add feature"


class TestCompare:
    def test_compare_refs(self):
        client = _mock_client()
        client._request.return_value = {
            "commits": [{"id": "abc123"}],
            "diffs": [],
        }
        result = client.compare(42, "v1.0.0", "v2.0.0")
        assert "commits" in result


# ── Inspector Tests ─────────────────────────────────────────────────────────


def _mock_inspector():
    """Create an inspector with a mocked client."""
    client = _mock_client()
    return GitLabInspector(client), client


class TestInspectorAuthFlow:
    """Auth must be checked FIRST, before any data fetch."""

    def test_auth_failure_stops_immediately(self):
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "Invalid token",
            kind=GitLabErrorKind.AUTH_FAILED,
        )
        result = inspector.inspect("group/repo")
        assert result.is_authenticated is False
        assert result.is_accessible is False
        assert "auth_failed" in result.error_kind
        # Should only have called validate_token (1 call), not continued
        assert client._request.call_count == 1

    def test_project_not_found(self):
        inspector, client = _mock_inspector()
        # validate_token succeeds
        client._request.side_effect = [
            {"username": "admin"},  # validate_token
            GitLabError("Not found", kind=GitLabErrorKind.NOT_FOUND),  # get_project
        ]
        result = inspector.inspect("nonexistent/repo")
        assert result.is_authenticated is True
        assert result.is_accessible is False
        assert "not_found" in result.error_kind

    def test_successful_inspection(self):
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
        assert result.is_authenticated is True
        assert result.is_accessible is True
        assert result.default_branch == "main"
        assert len(result.branches) == 2
        assert len(result.tags) == 1
        assert any(b.name == "release/2026.04" for b in result.branches)

    def test_branch_list_failure_is_non_fatal(self):
        """Even if branch listing fails, we still return project info."""
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
        assert result.is_accessible is True
        assert len(result.branches) == 0
        assert any("Could not list branches" in d for d in result.diagnostics)


class TestBranchLookup:
    """Targeted branch lookup must handle all cases."""

    def test_found(self):
        inspector, client = _mock_inspector()
        client._request.return_value = {
            "name": "release/2026.04",
            "commit": {"id": "abc123", "committed_date": "2024-01-01"},
            "default": False,
            "protected": False,
        }
        result = inspector.lookup_branch(42, "release/2026.04")
        assert result.found is True
        assert result.branch is not None
        assert result.branch.name == "release/2026.04"

    def test_not_found(self):
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "Not found",
            kind=GitLabErrorKind.NOT_FOUND,
        )
        result = inspector.lookup_branch(42, "nonexistent/branch")
        assert result.found is False
        assert "not_found" in result.error_kind
        assert "does not exist" in result.error

    def test_auth_failure_on_lookup(self):
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "401",
            kind=GitLabErrorKind.AUTH_FAILED,
        )
        result = inspector.lookup_branch(42, "main")
        assert result.found is False
        assert "auth_failed" in result.error_kind


class TestTagLookup:
    def test_found(self):
        inspector, client = _mock_inspector()
        client._request.return_value = {
            "name": "v1.0.0",
            "commit": {"id": "abc123", "committed_date": "2024-01-01"},
            "message": "Release",
        }
        result = inspector.lookup_tag(42, "v1.0.0")
        assert result.found is True
        assert result.tag.name == "v1.0.0"

    def test_not_found(self):
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "Not found",
            kind=GitLabErrorKind.NOT_FOUND,
        )
        result = inspector.lookup_tag(42, "nonexistent")
        assert result.found is False


class TestCheckExists:
    def test_branch_exists(self):
        inspector, client = _mock_inspector()
        client._request.return_value = {
            "name": "release/2026.04",
            "commit": {"id": "abc123"},
            "default": False,
            "protected": False,
        }
        assert inspector.check_branch_exists(42, "release/2026.04") is True

    def test_branch_not_exists(self):
        inspector, client = _mock_inspector()
        client._request.side_effect = GitLabError(
            "Not found",
            kind=GitLabErrorKind.NOT_FOUND,
        )
        assert inspector.check_branch_exists(42, "nope") is False


# ── Inspector from_env/from_config Tests ────────────────────────────────────


class TestInspectorConstruction:
    def test_from_config(self):
        inspector = GitLabInspector.from_config(
            gitlab_url="https://gitlab.example.com",
            gitlab_token="glpat-test",
        )
        assert inspector._client._base_url == "https://gitlab.example.com"
        assert inspector._client._token == "glpat-test"

    def test_from_env_missing_url(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(GitLabError) as exc_info:
                GitLabInspector.from_env()
            assert "RELEASEPILOT_GITLAB_URL" in str(exc_info.value)

    def test_from_env_with_values(self):
        env = {
            "RELEASEPILOT_GITLAB_URL": "https://gitlab.example.com",
            "RELEASEPILOT_GITLAB_TOKEN": "glpat-test",
        }
        with patch.dict("os.environ", env, clear=True):
            inspector = GitLabInspector.from_env()
            assert inspector._client._base_url == "https://gitlab.example.com"

    def test_from_env_ssl_verify_disabled(self):
        env = {
            "RELEASEPILOT_GITLAB_URL": "https://gitlab.example.com",
            "RELEASEPILOT_GITLAB_TOKEN": "glpat-test",
            "RELEASEPILOT_GITLAB_SSL_VERIFY": "false",
        }
        with patch.dict("os.environ", env, clear=True):
            inspector = GitLabInspector.from_env()
            assert inspector._client._verify_ssl is False


# ── Settings Tests ──────────────────────────────────────────────────────────


class TestSettingsGitLab:
    """Settings dataclass must support GitLab fields."""

    def test_default_values(self):
        from releasepilot.config.settings import Settings

        s = Settings()
        assert s.gitlab_url == ""
        assert s.gitlab_token == ""
        assert s.gitlab_project == ""
        assert s.gitlab_ssl_verify is True
        assert s.is_gitlab_source is False

    def test_gitlab_source_detected(self):
        from releasepilot.config.settings import Settings

        s = Settings(
            gitlab_url="https://gitlab.example.com",
            gitlab_project="group/repo",
        )
        assert s.is_gitlab_source is True

    def test_gitlab_source_needs_both(self):
        from releasepilot.config.settings import Settings

        # URL only — not a gitlab source
        s = Settings(gitlab_url="https://gitlab.example.com")
        assert s.is_gitlab_source is False


# ── Config File Tests ───────────────────────────────────────────────────────


class TestConfigKnownKeys:
    """Config file validator must accept gitlab_* keys."""

    def test_gitlab_keys_are_known(self):
        from releasepilot.config.file_config import _KNOWN_KEYS

        assert "gitlab_url" in _KNOWN_KEYS
        assert "gitlab-url" in _KNOWN_KEYS
        assert "gitlab_token" in _KNOWN_KEYS
        assert "gitlab-token" in _KNOWN_KEYS
        assert "gitlab_project" in _KNOWN_KEYS
        assert "gitlab-project" in _KNOWN_KEYS
        assert "gitlab_ssl_verify" in _KNOWN_KEYS
        assert "gitlab-ssl-verify" in _KNOWN_KEYS


# ── Web API Tests ───────────────────────────────────────────────────────────


class TestWebGitLabEndpoints:
    """Test the FastAPI GitLab endpoints with mocked inspector."""

    @pytest.fixture
    def client(self):
        """Create a test client with auth disabled for simplicity."""
        from releasepilot.web.server import create_app

        os_env = {
            "RELEASEPILOT_API_KEY": "",  # disable auth
        }
        with patch.dict("os.environ", os_env):
            app = create_app()

        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_validate_no_gitlab_url(self, client):
        resp = client.post("/api/gitlab/validate", json={})
        assert resp.status_code == 400
        assert "GitLab URL not configured" in resp.json()["error"]

    def test_validate_no_gitlab_token(self, client):
        resp = client.post(
            "/api/gitlab/validate",
            json={"gitlab_url": "https://gitlab.example.com"},
        )
        assert resp.status_code == 400
        assert "GitLab token not configured" in resp.json()["error"]

    def test_inspect_missing_project(self, client):
        resp = client.post(
            "/api/gitlab/inspect",
            json={},
        )
        assert resp.status_code == 400

    def test_config_accepts_gitlab_fields(self, client):
        """PUT /api/config must accept gitlab_url, gitlab_token, gitlab_project."""
        resp = client.put(
            "/api/config",
            json={
                "gitlab_url": "https://gitlab.example.com",
                "gitlab_token": "glpat-test",
                "gitlab_project": "group/repo",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # Token must NOT be exposed
        assert "gitlab_token" not in data["config"]
        assert data["config"].get("gitlab_token_set") is True
        assert data["config"]["gitlab_url"] == "https://gitlab.example.com"

    def test_config_accepts_gitlab_ssl_verify(self, client):
        """gitlab_ssl_verify is boolean, not string."""
        resp = client.put(
            "/api/config",
            json={
                "gitlab_ssl_verify": False,
            },
        )
        assert resp.status_code == 200

    def test_config_rejects_non_bool_ssl_verify(self, client):
        resp = client.put(
            "/api/config",
            json={
                "gitlab_ssl_verify": "false",
            },
        )
        assert resp.status_code == 400
        assert "boolean" in resp.json()["error"]


# ── Data Model Tests ────────────────────────────────────────────────────────


class TestDataModels:
    """Frozen dataclasses must be hashable and comparable."""

    def test_branch_frozen(self):
        b = GitLabBranch(name="main", commit_sha="abc")
        with pytest.raises(AttributeError):
            b.name = "other"  # type: ignore[misc]

    def test_tag_frozen(self):
        t = GitLabTag(name="v1.0", commit_sha="abc")
        with pytest.raises(AttributeError):
            t.name = "other"  # type: ignore[misc]

    def test_project_frozen(self):
        p = GitLabProject(id=1, name="test", path_with_namespace="g/t")
        with pytest.raises(AttributeError):
            p.id = 2  # type: ignore[misc]

    def test_commit_frozen(self):
        c = GitLabCommit(
            sha="abc",
            short_id="abc",
            title="t",
            message="m",
            author_name="a",
            authored_date="d",
            committed_date="d",
        )
        with pytest.raises(AttributeError):
            c.sha = "other"  # type: ignore[misc]

    def test_inspection_defaults(self):
        r = GitLabRepoInspection()
        assert r.project is None
        assert r.branches == ()
        assert r.tags == ()
        assert r.is_accessible is False

    def test_branch_lookup_result_defaults(self):
        r = BranchLookupResult()
        assert r.found is False
        assert r.branch is None

    def test_tag_lookup_result_defaults(self):
        r = TagLookupResult()
        assert r.found is False
        assert r.tag is None


# ── Integration: Client _request with Real HTTP Mock ───────────────────────


class TestClientRequestMocking:
    """Verify _request attaches PRIVATE-TOKEN to every call."""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_token_in_every_request(self, mock_urlopen):
        """PRIVATE-TOKEN header must be present on all requests."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"username":"test"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitLabClient(
            base_url="https://gitlab.example.com",
            token="glpat-secret-token",
        )
        client.validate_token()

        # Check the Request object
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Private-token") == "glpat-secret-token"

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_url_encoding_in_real_path(self, mock_urlopen):
        """Slash-containing branch names must be encoded in the URL."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(
            {
                "name": "release/2026.04",
                "commit": {"id": "abc123", "committed_date": ""},
                "default": False,
                "protected": False,
            }
        ).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitLabClient(
            base_url="https://gitlab.example.com",
            token="glpat-test",
        )
        branch = client.get_branch(42, "release/2026.04")

        # The URL must contain the encoded ref
        req = mock_urlopen.call_args[0][0]
        assert "release%2F2026.04" in req.full_url
        assert branch.name == "release/2026.04"

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_http_401_raises_auth_error(self, mock_urlopen):
        http_err = urllib.error.HTTPError(
            url="https://gitlab.example.com/api/v4/user",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b"Unauthorized"),
        )
        mock_urlopen.side_effect = http_err

        client = GitLabClient(base_url="https://gitlab.example.com", token="bad")
        with pytest.raises(GitLabError) as exc_info:
            client.validate_token()
        assert exc_info.value.kind == GitLabErrorKind.AUTH_FAILED

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_url_error_raises_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        client = GitLabClient(base_url="https://gitlab.example.com", token="tok")
        with pytest.raises(GitLabError) as exc_info:
            client.validate_token()
        assert exc_info.value.kind == GitLabErrorKind.NETWORK_ERROR

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_ssl_error_raises_ssl_error(self, mock_urlopen):
        ssl_err = ssl.SSLError("certificate verify failed")
        mock_urlopen.side_effect = urllib.error.URLError(ssl_err)

        client = GitLabClient(base_url="https://gitlab.example.com", token="tok")
        with pytest.raises(GitLabError) as exc_info:
            client.validate_token()
        assert exc_info.value.kind == GitLabErrorKind.SSL_ERROR


# ── Cache Integration Tests ────────────────────────────────────────────────


class TestClientCaching:
    """Verify caching prevents redundant API calls."""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_second_call_uses_cache(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(
            {
                "id": 42,
                "name": "repo",
                "path_with_namespace": "g/r",
                "default_branch": "main",
                "web_url": "",
                "visibility": "",
                "description": "",
            }
        ).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitLabClient(
            base_url="https://gitlab.example.com",
            token="tok",
        )
        client.get_project(42)
        client.get_project(42)  # Should hit cache

        # Only one actual HTTP call
        assert mock_urlopen.call_count == 1

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_invalidate_forces_refetch(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(
            {
                "id": 42,
                "name": "repo",
                "path_with_namespace": "g/r",
                "default_branch": "main",
                "web_url": "",
                "visibility": "",
                "description": "",
            }
        ).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = GitLabClient(
            base_url="https://gitlab.example.com",
            token="tok",
        )
        client.get_project(42)
        client.invalidate_cache(42)
        client.get_project(42)  # Should make a new call

        assert mock_urlopen.call_count == 2
