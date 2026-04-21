"""Tests for security, authentication, middleware, and server infrastructure.

Each test class covers a specific concern such as auth, CORS, rate limiting,
input validation, and server configuration.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from releasepilot.web.server import create_app

# ═══════════════════════════════════════════════════════════════════════════════
# API key authentication
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiKeyAuth:
    """Verify that API key authentication works on protected endpoints."""

    """GIVEN Protected endpoints return 401 when API key is required but missing"""

    def test_generate_rejected_without_api_key(self):
        """WHEN the test exercises generate rejected without api key"""
        with patch.dict(os.environ, {"RELEASEPILOT_API_KEY": "test-secret-key"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/generate", json={})
            assert resp.status_code == 401
            assert resp.json()["error"] == "Unauthorized"

    """GIVEN Protected endpoints accept requests with the correct Bearer token"""

    def test_generate_accepted_with_correct_key(self):
        """WHEN the test exercises generate accepted with correct key"""
        with patch.dict(os.environ, {"RELEASEPILOT_API_KEY": "test-secret-key"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/generate",
                json={},
                headers={"Authorization": "Bearer test-secret-key"},
            )
            # Should not be 401 - may be 409 or 200 depending on state
            assert resp.status_code != 401

    """GIVEN When no API key is configured, requests pass through without auth"""

    def test_no_auth_when_key_not_configured(self):
        """WHEN the test exercises no auth when key not configured"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RELEASEPILOT_API_KEY", None)
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/generate", json={})
            # Should not be 401
            assert resp.status_code != 401

    """GIVEN PUT /api/config also requires authentication"""

    def test_config_update_requires_auth(self):
        """WHEN the test exercises config update requires auth"""
        with patch.dict(os.environ, {"RELEASEPILOT_API_KEY": "mykey"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.put("/api/config", json={"language": "pl"})
            assert resp.status_code == 401

    """GIVEN POST /api/dashboard also requires authentication"""

    def test_dashboard_regen_requires_auth(self):
        """WHEN the test exercises dashboard regen requires auth"""
        with patch.dict(os.environ, {"RELEASEPILOT_API_KEY": "mykey"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/dashboard", json={})
            assert resp.status_code == 401


class TestCorsConfiguration:
    """Verify CORS middleware is applied when configured."""

    """GIVEN CORS headers appear when RELEASEPILOT_CORS_ORIGINS is set"""

    def test_cors_headers_present_when_configured(self):
        """WHEN the test exercises cors headers present when configured"""
        with patch.dict(os.environ, {"RELEASEPILOT_CORS_ORIGINS": "https://example.com"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.options(
                "/api/status",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert resp.status_code == 200
            assert "access-control-allow-origin" in resp.headers

    """GIVEN No CORS headers when env var is not set"""

    def test_no_cors_headers_when_not_configured(self):
        """WHEN the test exercises no cors headers when not configured"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RELEASEPILOT_CORS_ORIGINS", None)
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/status")
            assert "access-control-allow-origin" not in resp.headers


class TestRateLimiting:
    """Verify rate limiting on API endpoints."""

    """GIVEN Sending too many requests returns 429"""

    def test_rate_limit_rejects_after_threshold(self):
        """WHEN the test exercises rate limit rejects after threshold"""
        from releasepilot.web import server as srv

        original_max = srv._RATE_LIMIT_MAX
        try:
            srv._RATE_LIMIT_MAX = 3  # Lower for testing
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            responses = []
            for _ in range(5):
                resp = client.post("/api/generate", json={})
                responses.append(resp.status_code)
            assert 429 in responses
        finally:
            srv._RATE_LIMIT_MAX = original_max


class TestRepoPathValidation:
    """Verify repo_path is validated to prevent injection attacks."""

    """GIVEN Repo paths with dangerous characters are rejected"""

    def test_rejects_shell_metacharacters(self):
        """WHEN the test exercises rejects shell metacharacters"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/generate", json={"repo_path": "/tmp; rm -rf /"})
        """THEN the expected behavior for rejects shell metacharacters is observed"""
        assert resp.status_code == 400
        assert "unsafe" in resp.json()["error"].lower()

    """GIVEN a scenario for rejects backticks"""

    def test_rejects_backticks(self):
        """WHEN the test exercises rejects backticks"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/generate", json={"repo_path": "/tmp/`whoami`"})
        """THEN the expected behavior for rejects backticks is observed"""
        assert resp.status_code == 400

    """GIVEN a scenario for rejects pipe"""

    def test_rejects_pipe(self):
        """WHEN the test exercises rejects pipe"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/generate", json={"repo_path": "/tmp | cat /etc/passwd"})
        """THEN the expected behavior for rejects pipe is observed"""
        assert resp.status_code == 400

    """GIVEN a scenario for rejects nonexistent path"""

    def test_rejects_nonexistent_path(self):
        """WHEN the test exercises rejects nonexistent path"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/generate", json={"repo_path": "/nonexistent/fake/path"})
        """THEN the expected behavior for rejects nonexistent path is observed"""
        assert resp.status_code == 400

    """GIVEN PUT /api/config also validates repo_path"""

    def test_config_update_validates_repo_path(self):
        """WHEN the test exercises config update validates repo path"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put("/api/config", json={"repo_path": "/tmp;ls"})
        """THEN the expected behavior for config update validates repo path is observed"""
        assert resp.status_code == 400


class TestRequestBodySizeLimit:
    """Verify large request bodies are rejected."""

    """GIVEN A request exceeding the body size limit gets 413"""

    def test_oversized_body_returns_413(self):
        """WHEN the test exercises oversized body returns 413"""
        from releasepilot.web import server as srv

        original = srv.MAX_REQUEST_BODY_BYTES
        try:
            srv.MAX_REQUEST_BODY_BYTES = 100  # Very small for testing
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            big_payload = {"data": "x" * 200}
            resp = client.post(
                "/api/generate",
                json=big_payload,
                headers={"Content-Length": "500"},
            )
            assert resp.status_code == 413
        finally:
            srv.MAX_REQUEST_BODY_BYTES = original


class TestInputSanitization:
    """Verify renderers sanitize user-supplied text."""

    """GIVEN a scenario for pdf esc handles html entities"""

    def test_pdf_esc_handles_html_entities(self):
        """WHEN the test exercises pdf esc handles html entities"""
        from releasepilot.rendering.pdf import _esc

        result = _esc('<script>alert("xss")</script>')
        """THEN the expected behavior for pdf esc handles html entities is observed"""
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    """GIVEN a scenario for jinja autoescape is enabled"""

    def test_jinja_autoescape_is_enabled(self):
        """WHEN the test exercises jinja autoescape is enabled"""
        from releasepilot.dashboard.renderer import DashboardRenderer

        renderer = DashboardRenderer()
        """THEN the expected behavior for jinja autoescape is enabled is observed"""
        assert renderer._env.autoescape is not False


class TestCloneURLValidation:
    """Verify only HTTPS URLs are accepted for cloning."""

    """GIVEN a scenario for ssh url rejected"""

    def test_ssh_url_rejected(self):
        """WHEN the test exercises ssh url rejected"""
        from releasepilot.cli.guide import _step_clone_repo

        result = _step_clone_repo("git@github.com:user/repo.git")
        """THEN the expected behavior for ssh url rejected is observed"""
        assert result is None

    """GIVEN a scenario for http url rejected"""

    def test_http_url_rejected(self):
        """WHEN the test exercises http url rejected"""
        from releasepilot.cli.guide import _step_clone_repo

        result = _step_clone_repo("http://github.com/user/repo.git")
        """THEN the expected behavior for http url rejected is observed"""
        assert result is None

    """GIVEN a scenario for git protocol url rejected"""

    def test_git_protocol_url_rejected(self):
        """WHEN the test exercises git protocol url rejected"""
        from releasepilot.cli.guide import _step_clone_repo

        result = _step_clone_repo("git://github.com/user/repo.git")
        """THEN the expected behavior for git protocol url rejected is observed"""
        assert result is None


class TestAccentColorValidation:
    """Verify accent_color format is validated in config."""

    """GIVEN a scenario for valid hex color no warning"""

    def test_valid_hex_color_no_warning(self):
        """WHEN the test exercises valid hex color no warning"""
        from releasepilot.config.file_config import validate_config

        warnings = validate_config({"accent_color": "#FB6400"})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        """THEN the expected behavior for valid hex color no warning is observed"""
        assert len(color_warnings) == 0

    """GIVEN a scenario for invalid hex color warns"""

    def test_invalid_hex_color_warns(self):
        """WHEN the test exercises invalid hex color warns"""
        from releasepilot.config.file_config import validate_config

        warnings = validate_config({"accent_color": "not-a-color"})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        """THEN the expected behavior for invalid hex color warns is observed"""
        assert len(color_warnings) == 1

    """GIVEN a scenario for short hex warns"""

    def test_short_hex_warns(self):
        """WHEN the test exercises short hex warns"""
        from releasepilot.config.file_config import validate_config

        warnings = validate_config({"accent_color": "#FFF"})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        """THEN the expected behavior for short hex warns is observed"""
        assert len(color_warnings) == 1

    """GIVEN a scenario for missing hash warns"""

    def test_missing_hash_warns(self):
        """WHEN the test exercises missing hash warns"""
        from releasepilot.config.file_config import validate_config

        warnings = validate_config({"accent_color": "FB6400"})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        """THEN the expected behavior for missing hash warns is observed"""
        assert len(color_warnings) == 1

    """GIVEN a scenario for empty accent color ok"""

    def test_empty_accent_color_ok(self):
        """WHEN the test exercises empty accent color ok"""
        from releasepilot.config.file_config import validate_config

        warnings = validate_config({"accent_color": ""})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        """THEN the expected behavior for empty accent color ok is observed"""
        assert len(color_warnings) == 0
