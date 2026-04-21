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
import urllib.error
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


# ── Integration: Client _request with Real HTTP Mock ───────────────────────


class TestClientConstruction:
    """Token must be required - no unauthenticated clients."""

    """GIVEN a scenario for no token raises"""

    def test_no_token_raises(self):
        """WHEN the test exercises no token raises"""
        """THEN the expected behavior for no token raises is observed"""
        with pytest.raises(GitLabError) as exc_info:
            GitLabClient(base_url="https://gitlab.example.com", token="")
        assert exc_info.value.kind == GitLabErrorKind.AUTH_FAILED

    """GIVEN a scenario for valid construction"""

    def test_valid_construction(self):
        """WHEN the test exercises valid construction"""
        client = GitLabClient(
            base_url="https://gitlab.example.com",
            token="glpat-test-token",
        )
        """THEN the expected behavior for valid construction is observed"""
        assert client._base_url == "https://gitlab.example.com"
        assert client._token == "glpat-test-token"

    """GIVEN a scenario for trailing slash stripped"""

    def test_trailing_slash_stripped(self):
        """WHEN the test exercises trailing slash stripped"""
        client = GitLabClient(
            base_url="https://gitlab.example.com/",
            token="tok",
        )
        """THEN the expected behavior for trailing slash stripped is observed"""
        assert client._base_url == "https://gitlab.example.com"


class TestValidateToken:
    """GIVEN a scenario for returns user info"""

    def test_returns_user_info(self):
        """WHEN the test exercises returns user info"""
        client = _mock_client()
        client._request.return_value = {"username": "admin", "name": "Admin User"}
        result = client.validate_token()
        """THEN the expected behavior for returns user info is observed"""
        assert result["username"] == "admin"
        client._request.assert_called_once_with("GET", "/user", use_cache=False)


class TestGetProject:
    """GIVEN a scenario for by path"""

    def test_by_path(self):
        """WHEN the test exercises by path"""
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
        """THEN the expected behavior for by path is observed"""
        assert project.id == 42
        assert project.path_with_namespace == "EMEA/GAD/MerchantPortal/UI/additional-reports"
        assert project.default_branch == "main"
        assert project.visibility == "internal"

        # Verify the path was encoded
        call_args = client._request.call_args
        assert "EMEA%2FGAD%2FMerchantPortal%2FUI%2Fadditional-reports" in call_args[0][1]

    """GIVEN a scenario for by id"""

    def test_by_id(self):
        """WHEN the test exercises by id"""
        client = _mock_client()
        client._request.return_value = {"id": 42, "name": "repo", "path_with_namespace": "g/r"}
        project = client.get_project(42)
        """THEN the expected behavior for by id is observed"""
        assert project.id == 42
        call_args = client._request.call_args
        assert "/projects/42" in call_args[0][1]


class TestListBranches:
    """GIVEN a scenario for returns branches"""

    def test_returns_branches(self):
        """WHEN the test exercises returns branches"""
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
        """THEN the expected behavior for returns branches is observed"""
        assert len(branches) == 2
        assert branches[0].name == "main"
        assert branches[0].is_default is True
        assert branches[1].name == "release/2026.04"

    """GIVEN a scenario for empty list"""

    def test_empty_list(self):
        """WHEN the test exercises empty list"""
        client = _mock_client()
        client._request.return_value = []
        branches = client.list_branches(42)
        """THEN the expected behavior for empty list is observed"""
        assert branches == []

    """GIVEN a scenario for none response"""

    def test_none_response(self):
        """WHEN the test exercises none response"""
        client = _mock_client()
        client._request.return_value = None
        branches = client.list_branches(42)
        """THEN the expected behavior for none response is observed"""
        assert branches == []


class TestGetBranch:
    """GIVEN release/2026.04 must be found, not 404'd"""

    def test_branch_with_slash(self):
        """WHEN the test exercises branch with slash"""
        client = _mock_client()
        client._request.return_value = {
            "name": "release/2026.04",
            "commit": {"id": "abc123", "committed_date": "2024-01-01T00:00:00Z"},
            "default": False,
            "protected": True,
        }
        branch = client.get_branch(42, "release/2026.04")
        """THEN the expected behavior for branch with slash is observed"""
        assert branch.name == "release/2026.04"
        assert branch.commit_sha == "abc123"

        # Verify encoding in the API path
        call_args = client._request.call_args
        api_path = call_args[0][1]
        assert "release%2F2026.04" in api_path
        assert "release/2026.04" not in api_path  # Must NOT have raw slash

    """GIVEN a scenario for simple branch"""

    def test_simple_branch(self):
        """WHEN the test exercises simple branch"""
        client = _mock_client()
        client._request.return_value = {
            "name": "main",
            "commit": {"id": "abc123", "committed_date": "2024-01-01T00:00:00Z"},
            "default": True,
            "protected": True,
        }
        branch = client.get_branch(42, "main")
        """THEN the expected behavior for simple branch is observed"""
        assert branch.name == "main"
        assert branch.is_default is True


class TestGetTag:
    """GIVEN a scenario for simple tag"""

    def test_simple_tag(self):
        """WHEN the test exercises simple tag"""
        client = _mock_client()
        client._request.return_value = {
            "name": "v1.0.0",
            "commit": {"id": "abc123", "committed_date": "2024-01-01T00:00:00Z"},
            "message": "Release 1.0",
        }
        tag = client.get_tag(42, "v1.0.0")
        """THEN the expected behavior for simple tag is observed"""
        assert tag.name == "v1.0.0"
        assert tag.message == "Release 1.0"

    """GIVEN a scenario for tag with slash"""

    def test_tag_with_slash(self):
        """WHEN the test exercises tag with slash"""
        client = _mock_client()
        client._request.return_value = {
            "name": "release/v1.0",
            "commit": {"id": "def456"},
        }
        _ = client.get_tag(42, "release/v1.0")
        # Verify encoding
        call_args = client._request.call_args
        """THEN the expected behavior for tag with slash is observed"""
        assert "release%2Fv1.0" in call_args[0][1]


class TestListCommits:
    """GIVEN a scenario for returns commits"""

    def test_returns_commits(self):
        """WHEN the test exercises returns commits"""
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
        """THEN the expected behavior for returns commits is observed"""
        assert len(commits) == 1
        assert commits[0].title == "feat: add feature"


class TestCompare:
    """GIVEN a scenario for compare refs"""

    def test_compare_refs(self):
        """WHEN the test exercises compare refs"""
        client = _mock_client()
        client._request.return_value = {
            "commits": [{"id": "abc123"}],
            "diffs": [],
        }
        result = client.compare(42, "v1.0.0", "v2.0.0")
        """THEN the expected behavior for compare refs is observed"""
        assert "commits" in result


class TestClientRequestMocking:
    """Verify _request attaches PRIVATE-TOKEN to every call."""

    """GIVEN PRIVATE-TOKEN header must be present on all requests"""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_token_in_every_request(self, mock_urlopen):
        """WHEN the test exercises token in every request"""
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
        """THEN the expected behavior for token in every request is observed"""
        assert req.get_header("Private-token") == "glpat-secret-token"

    """GIVEN Slash-containing branch names must be encoded in the URL"""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_url_encoding_in_real_path(self, mock_urlopen):
        """WHEN the test exercises url encoding in real path"""
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
        """THEN the expected behavior for url encoding in real path is observed"""
        assert "release%2F2026.04" in req.full_url
        assert branch.name == "release/2026.04"

    """GIVEN a scenario for http 401 raises auth error"""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_http_401_raises_auth_error(self, mock_urlopen):
        """WHEN the test exercises http 401 raises auth error"""
        http_err = urllib.error.HTTPError(
            url="https://gitlab.example.com/api/v4/user",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b"Unauthorized"),
        )
        mock_urlopen.side_effect = http_err

        client = GitLabClient(base_url="https://gitlab.example.com", token="bad")
        """THEN the expected behavior for http 401 raises auth error is observed"""
        with pytest.raises(GitLabError) as exc_info:
            client.validate_token()
        assert exc_info.value.kind == GitLabErrorKind.AUTH_FAILED

    """GIVEN a scenario for url error raises network error"""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_url_error_raises_network_error(self, mock_urlopen):
        """WHEN the test exercises url error raises network error"""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        client = GitLabClient(base_url="https://gitlab.example.com", token="tok")
        """THEN the expected behavior for url error raises network error is observed"""
        with pytest.raises(GitLabError) as exc_info:
            client.validate_token()
        assert exc_info.value.kind == GitLabErrorKind.NETWORK_ERROR

    """GIVEN a scenario for ssl error raises ssl error"""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_ssl_error_raises_ssl_error(self, mock_urlopen):
        """WHEN the test exercises ssl error raises ssl error"""
        ssl_err = ssl.SSLError("certificate verify failed")
        mock_urlopen.side_effect = urllib.error.URLError(ssl_err)

        client = GitLabClient(base_url="https://gitlab.example.com", token="tok")
        """THEN the expected behavior for ssl error raises ssl error is observed"""
        with pytest.raises(GitLabError) as exc_info:
            client.validate_token()
        assert exc_info.value.kind == GitLabErrorKind.SSL_ERROR


class TestClientCaching:
    """Verify caching prevents redundant API calls."""

    """GIVEN a scenario for second call uses cache"""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_second_call_uses_cache(self, mock_urlopen):
        """WHEN the test exercises second call uses cache"""
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
        """THEN the expected behavior for second call uses cache is observed"""
        assert mock_urlopen.call_count == 1

    """GIVEN a scenario for invalidate forces refetch"""

    @patch("releasepilot.sources.gitlab.urllib.request.urlopen")
    def test_invalidate_forces_refetch(self, mock_urlopen):
        """WHEN the test exercises invalidate forces refetch"""
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

        """THEN the expected behavior for invalidate forces refetch is observed"""
        assert mock_urlopen.call_count == 2
