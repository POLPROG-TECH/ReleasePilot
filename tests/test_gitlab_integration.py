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


class TestSettingsGitLab:
    """Settings dataclass must support GitLab fields."""

    """GIVEN a scenario for default values"""

    def test_default_values(self):
        """WHEN the test exercises default values"""
        from releasepilot.config.settings import Settings

        s = Settings()
        """THEN the expected behavior for default values is observed"""
        assert s.gitlab_url == ""
        assert s.gitlab_token == ""
        assert s.gitlab_project == ""
        assert s.gitlab_ssl_verify is True
        assert s.is_gitlab_source is False

    """GIVEN a scenario for gitlab source detected"""

    def test_gitlab_source_detected(self):
        """WHEN the test exercises gitlab source detected"""
        from releasepilot.config.settings import Settings

        s = Settings(
            gitlab_url="https://gitlab.example.com",
            gitlab_project="group/repo",
        )
        """THEN the expected behavior for gitlab source detected is observed"""
        assert s.is_gitlab_source is True

    """GIVEN a scenario for gitlab source needs both"""

    def test_gitlab_source_needs_both(self):
        """WHEN the test exercises gitlab source needs both"""
        from releasepilot.config.settings import Settings

        # URL only - not a gitlab source
        s = Settings(gitlab_url="https://gitlab.example.com")
        """THEN the expected behavior for gitlab source needs both is observed"""
        assert s.is_gitlab_source is False


class TestConfigKnownKeys:
    """Config file validator must accept gitlab_* keys."""

    """GIVEN a scenario for gitlab keys are known"""

    def test_gitlab_keys_are_known(self):
        """WHEN the test exercises gitlab keys are known"""
        from releasepilot.config.file_config import _KNOWN_KEYS

        """THEN the expected behavior for gitlab keys are known is observed"""
        assert "gitlab_url" in _KNOWN_KEYS
        assert "gitlab-url" in _KNOWN_KEYS
        assert "gitlab_token" in _KNOWN_KEYS
        assert "gitlab-token" in _KNOWN_KEYS
        assert "gitlab_project" in _KNOWN_KEYS
        assert "gitlab-project" in _KNOWN_KEYS
        assert "gitlab_ssl_verify" in _KNOWN_KEYS
        assert "gitlab-ssl-verify" in _KNOWN_KEYS


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

    """GIVEN a scenario for validate no gitlab url"""

    def test_validate_no_gitlab_url(self, client):
        """WHEN the test exercises validate no gitlab url"""
        resp = client.post("/api/gitlab/validate", json={})
        """THEN the expected behavior for validate no gitlab url is observed"""
        assert resp.status_code == 400
        assert "GitLab URL not configured" in resp.json()["error"]

    """GIVEN a scenario for validate no gitlab token"""

    def test_validate_no_gitlab_token(self, client):
        """WHEN the test exercises validate no gitlab token"""
        resp = client.post(
            "/api/gitlab/validate",
            json={"gitlab_url": "https://gitlab.example.com"},
        )
        """THEN the expected behavior for validate no gitlab token is observed"""
        assert resp.status_code == 400
        assert "GitLab token not configured" in resp.json()["error"]

    """GIVEN a scenario for inspect missing project"""

    def test_inspect_missing_project(self, client):
        """WHEN the test exercises inspect missing project"""
        resp = client.post(
            "/api/gitlab/inspect",
            json={},
        )
        """THEN the expected behavior for inspect missing project is observed"""
        assert resp.status_code == 400

    """GIVEN PUT /api/config must accept gitlab_url, gitlab_token, gitlab_project"""

    def test_config_accepts_gitlab_fields(self, client):
        """WHEN the test exercises config accepts gitlab fields"""
        resp = client.put(
            "/api/config",
            json={
                "gitlab_url": "https://gitlab.example.com",
                "gitlab_token": "glpat-test",
                "gitlab_project": "group/repo",
            },
        )
        """THEN the expected behavior for config accepts gitlab fields is observed"""
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # Token must NOT be exposed
        assert "gitlab_token" not in data["config"]
        assert data["config"].get("gitlab_token_set") is True
        assert data["config"]["gitlab_url"] == "https://gitlab.example.com"

    """GIVEN gitlab_ssl_verify is boolean, not string"""

    def test_config_accepts_gitlab_ssl_verify(self, client):
        """WHEN the test exercises config accepts gitlab ssl verify"""
        resp = client.put(
            "/api/config",
            json={
                "gitlab_ssl_verify": False,
            },
        )
        """THEN the expected behavior for config accepts gitlab ssl verify is observed"""
        assert resp.status_code == 200

    """GIVEN a scenario for config rejects non bool ssl verify"""

    def test_config_rejects_non_bool_ssl_verify(self, client):
        """WHEN the test exercises config rejects non bool ssl verify"""
        resp = client.put(
            "/api/config",
            json={
                "gitlab_ssl_verify": "false",
            },
        )
        """THEN the expected behavior for config rejects non bool ssl verify is observed"""
        assert resp.status_code == 400
        assert "boolean" in resp.json()["error"]
