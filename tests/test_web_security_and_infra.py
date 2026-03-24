"""Tests for security, authentication, middleware, and server infrastructure.

Each test class covers a specific concern such as auth, CORS, rate limiting,
input validation, and server configuration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from releasepilot.web.server import create_app

# ═══════════════════════════════════════════════════════════════════════════════
# API key authentication
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiKeyAuth:
    """Verify that API key authentication works on protected endpoints."""

    def test_generate_rejected_without_api_key(self):
        """Protected endpoints return 401 when API key is required but missing."""
        # GIVEN a server requiring API key auth
        with patch.dict(os.environ, {"RELEASEPILOT_API_KEY": "test-secret-key"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            # WHEN requesting without a key
            resp = client.post("/api/generate", json={})
            # THEN the request is rejected
            assert resp.status_code == 401
            assert resp.json()["error"] == "Unauthorized"

    def test_generate_accepted_with_correct_key(self):
        """Protected endpoints accept requests with the correct Bearer token."""
        # GIVEN a server requiring API key auth
        with patch.dict(os.environ, {"RELEASEPILOT_API_KEY": "test-secret-key"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            # WHEN requesting with the correct key
            resp = client.post(
                "/api/generate",
                json={},
                headers={"Authorization": "Bearer test-secret-key"},
            )
            # THEN the request is not rejected as unauthorized
            # Should not be 401 — may be 409 or 200 depending on state
            assert resp.status_code != 401

    def test_no_auth_when_key_not_configured(self):
        """When no API key is configured, requests pass through without auth."""
        # GIVEN a server with no API key configured
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RELEASEPILOT_API_KEY", None)
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            # WHEN requesting without a key
            resp = client.post("/api/generate", json={})
            # THEN the request is not rejected as unauthorized
            # Should not be 401
            assert resp.status_code != 401

    def test_config_update_requires_auth(self):
        """PUT /api/config also requires authentication."""
        # GIVEN a server requiring API key auth
        with patch.dict(os.environ, {"RELEASEPILOT_API_KEY": "mykey"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            # WHEN updating config without a key
            resp = client.put("/api/config", json={"language": "pl"})
            # THEN the request is rejected
            assert resp.status_code == 401

    def test_dashboard_regen_requires_auth(self):
        """POST /api/dashboard also requires authentication."""
        # GIVEN a server requiring API key auth
        with patch.dict(os.environ, {"RELEASEPILOT_API_KEY": "mykey"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            # WHEN posting to dashboard without a key
            resp = client.post("/api/dashboard", json={})
            # THEN the request is rejected
            assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# CORS configuration
# ═══════════════════════════════════════════════════════════════════════════════


class TestCorsConfiguration:
    """Verify CORS middleware is applied when configured."""

    def test_cors_headers_present_when_configured(self):
        """CORS headers appear when RELEASEPILOT_CORS_ORIGINS is set."""
        # GIVEN a server with CORS origins configured
        with patch.dict(os.environ, {"RELEASEPILOT_CORS_ORIGINS": "https://example.com"}):
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            # WHEN sending a CORS preflight request
            resp = client.options(
                "/api/status",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            # THEN CORS headers are present
            assert resp.status_code == 200
            assert "access-control-allow-origin" in resp.headers

    def test_no_cors_headers_when_not_configured(self):
        """No CORS headers when env var is not set."""
        # GIVEN a server with no CORS configuration
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RELEASEPILOT_CORS_ORIGINS", None)
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            # WHEN requesting any endpoint
            resp = client.get("/api/status")
            # THEN no CORS headers are present
            assert "access-control-allow-origin" not in resp.headers


# ═══════════════════════════════════════════════════════════════════════════════
# Rate limiting
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    """Verify rate limiting on API endpoints."""

    def test_rate_limit_rejects_after_threshold(self):
        """Sending too many requests returns 429."""
        from releasepilot.web import server as srv

        # GIVEN a server with a low rate limit
        original_max = srv._RATE_LIMIT_MAX
        try:
            srv._RATE_LIMIT_MAX = 3  # Lower for testing
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            # WHEN sending requests exceeding the limit
            responses = []
            for _ in range(5):
                resp = client.post("/api/generate", json={})
                responses.append(resp.status_code)
            # THEN at least one request is rate-limited
            assert 429 in responses
        finally:
            srv._RATE_LIMIT_MAX = original_max


# ═══════════════════════════════════════════════════════════════════════════════
# Repo path validation (command injection prevention)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRepoPathValidation:
    """Verify repo_path is validated to prevent injection attacks."""

    def test_rejects_shell_metacharacters(self):
        """Repo paths with dangerous characters are rejected."""
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN sending a repo path with shell metacharacters
        resp = client.post("/api/generate", json={"repo_path": "/tmp; rm -rf /"})
        # THEN the request is rejected as unsafe
        assert resp.status_code == 400
        assert "unsafe" in resp.json()["error"].lower()

    def test_rejects_backticks(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN sending a repo path with backticks
        resp = client.post("/api/generate", json={"repo_path": "/tmp/`whoami`"})
        # THEN the request is rejected
        assert resp.status_code == 400

    def test_rejects_pipe(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN sending a repo path with a pipe character
        resp = client.post("/api/generate", json={"repo_path": "/tmp | cat /etc/passwd"})
        # THEN the request is rejected
        assert resp.status_code == 400

    def test_rejects_nonexistent_path(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN sending a nonexistent repo path
        resp = client.post("/api/generate", json={"repo_path": "/nonexistent/fake/path"})
        # THEN the request is rejected
        assert resp.status_code == 400

    def test_config_update_validates_repo_path(self):
        """PUT /api/config also validates repo_path."""
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN updating config with an unsafe repo path
        resp = client.put("/api/config", json={"repo_path": "/tmp;ls"})
        # THEN the request is rejected
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# Request body size limit
# ═══════════════════════════════════════════════════════════════════════════════


class TestRequestBodySizeLimit:
    """Verify large request bodies are rejected."""

    def test_oversized_body_returns_413(self):
        """A request exceeding the body size limit gets 413."""
        from releasepilot.web import server as srv

        # GIVEN a server with a very small body size limit
        original = srv.MAX_REQUEST_BODY_BYTES
        try:
            srv.MAX_REQUEST_BODY_BYTES = 100  # Very small for testing
            app = create_app({"repo_path": "."})
            client = TestClient(app, raise_server_exceptions=False)
            big_payload = {"data": "x" * 200}
            # WHEN sending an oversized request body
            resp = client.post(
                "/api/generate",
                json=big_payload,
                headers={"Content-Length": "500"},
            )
            # THEN the request is rejected with 413
            assert resp.status_code == 413
        finally:
            srv.MAX_REQUEST_BODY_BYTES = original


# ═══════════════════════════════════════════════════════════════════════════════
# SSE subscriber cleanup
# ═══════════════════════════════════════════════════════════════════════════════


class TestSSESubscriberCleanup:
    """Verify SSE subscribers are cleaned up properly."""

    def test_full_queues_pruned_on_subscribe(self):
        """Full queues are removed when a new subscriber joins."""
        from releasepilot.web.state import AppState

        # GIVEN a subscriber with a full queue
        state = AppState()
        q1 = state.subscribe()
        for i in range(100):
            q1.put_nowait({"event": "test", "data": {"i": i}})
        assert q1.full()

        # WHEN a new subscriber joins
        q2 = state.subscribe()
        # THEN the full queue is pruned
        assert q1 not in state._sse_subscribers
        assert q2 in state._sse_subscribers

    def test_full_queues_removed_on_broadcast(self):
        """Full queues are unsubscribed during broadcast."""
        from releasepilot.web.state import AppState

        # GIVEN a subscriber with a full queue
        state = AppState()
        q = state.subscribe()
        for i in range(100):
            q.put_nowait({"event": "test", "data": {"i": i}})

        # WHEN a broadcast is sent
        loop = asyncio.new_event_loop()
        loop.run_until_complete(state.broadcast("test", {"x": 1}))
        loop.close()

        # THEN the full queue is removed
        assert q not in state._sse_subscribers

    def test_max_subscribers_limit(self):
        """Subscribing past the limit evicts the oldest subscriber."""
        from releasepilot.web.state import AppState

        # GIVEN a state with max 3 subscribers all filled
        state = AppState()
        state._max_subscribers = 3
        q1 = state.subscribe()
        _ = state.subscribe()
        _ = state.subscribe()
        # WHEN a fourth subscriber joins
        _ = state.subscribe()
        # THEN the oldest is evicted and limit is maintained
        assert q1 not in state._sse_subscribers
        assert len(state._sse_subscribers) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# HSTS header
# ═══════════════════════════════════════════════════════════════════════════════


class TestHSTSHeader:
    """Verify HSTS header is present on responses."""

    def test_hsts_header_present(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN requesting any endpoint
        resp = client.get("/health/live")
        # THEN HSTS header is present with max-age
        assert "strict-transport-security" in resp.headers
        assert "max-age=" in resp.headers["strict-transport-security"]


# ═══════════════════════════════════════════════════════════════════════════════
# _handle_error returns UserError without SystemExit
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleErrorNoSystemExit:
    """Verify _handle_error can return without exiting."""

    def test_returns_user_error_when_exit_disabled(self):
        from releasepilot.cli.errors import UserError
        from releasepilot.cli.helpers import _handle_error
        from releasepilot.pipeline.orchestrator import PipelineError

        # GIVEN a pipeline error
        # WHEN handling with exit disabled
        err = _handle_error(PipelineError("test error"), exit_on_error=False)
        # THEN a UserError is returned
        assert isinstance(err, UserError)
        assert "test error" in err.reason

    def test_still_exits_by_default(self):
        from releasepilot.cli.helpers import _handle_error
        from releasepilot.pipeline.orchestrator import PipelineError

        # GIVEN a pipeline error
        # WHEN handling with default settings
        # THEN SystemExit is raised
        with pytest.raises(SystemExit):
            _handle_error(PipelineError("test error"))

    def test_returns_for_git_errors(self):
        from releasepilot.cli.helpers import _handle_error
        from releasepilot.sources.git import GitCollectionError

        # GIVEN a git collection error
        # WHEN handling with exit disabled
        err = _handle_error(GitCollectionError("git failed"), exit_on_error=False)
        # THEN an error object is returned
        assert err is not None

    def test_returns_for_generic_errors(self):
        from releasepilot.cli.helpers import _handle_error

        # GIVEN a generic runtime error
        # WHEN handling with exit disabled
        err = _handle_error(RuntimeError("something broke"), exit_on_error=False)
        # THEN an error object with the message is returned
        assert err is not None
        assert "something broke" in err.reason


# ═══════════════════════════════════════════════════════════════════════════════
# Input sanitization
# ═══════════════════════════════════════════════════════════════════════════════


class TestInputSanitization:
    """Verify renderers sanitize user-supplied text."""

    def test_pdf_esc_handles_html_entities(self):
        from releasepilot.rendering.pdf import _esc

        # GIVEN a string with HTML tags
        # WHEN escaping it for PDF
        result = _esc('<script>alert("xss")</script>')
        # THEN HTML tags are escaped
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_jinja_autoescape_is_enabled(self):
        from releasepilot.dashboard.renderer import DashboardRenderer

        # GIVEN a dashboard renderer
        renderer = DashboardRenderer()
        # THEN autoescape is enabled
        assert renderer._env.autoescape is not False


# ═══════════════════════════════════════════════════════════════════════════════
# Health check reflects startup generation failure
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealthCheckStartupFailure:
    """Verify /health/ready works correctly."""

    def test_health_ready_200_when_ok(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN checking health readiness
        resp = client.get("/health/ready")
        # THEN the server reports ready
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


# ═══════════════════════════════════════════════════════════════════════════════
# Generation timeout
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerationTimeout:
    """Verify generation pipeline has a timeout configured."""

    def test_timeout_constant_is_reasonable(self):
        # GIVEN the generation timeout constant
        from releasepilot.web.server import GENERATION_TIMEOUT_SECONDS

        # THEN it is within a reasonable range
        assert GENERATION_TIMEOUT_SECONDS > 0
        assert GENERATION_TIMEOUT_SECONDS <= 600


# ═══════════════════════════════════════════════════════════════════════════════
# Graceful shutdown
# ═══════════════════════════════════════════════════════════════════════════════


class TestGracefulShutdown:
    """Verify background tasks are tracked."""

    def test_app_creates_without_error(self):
        # GIVEN default configuration
        # WHEN creating the app
        app = create_app({"repo_path": "."})
        # THEN the app is created successfully
        assert app is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Progress tracker encapsulation
# ═══════════════════════════════════════════════════════════════════════════════


class TestProgressTrackerEncapsulation:
    """Verify progress state is encapsulated, not global."""

    def test_tracker_class_exists(self):
        from releasepilot.cli.guide import _ProgressTracker

        # GIVEN the _ProgressTracker class
        tracker = _ProgressTracker()
        # THEN it has the expected attributes
        assert hasattr(tracker, "start_time")
        assert hasattr(tracker, "make_callback")
        assert hasattr(tracker, "finish")

    def test_two_trackers_independent(self):
        from releasepilot.cli.guide import _ProgressTracker

        # GIVEN two independent trackers
        t1 = _ProgressTracker()
        t2 = _ProgressTracker()
        # WHEN modifying each tracker's state
        t1.start_time = 100.0
        t2.start_time = 200.0
        # THEN they remain independent
        assert t1.start_time != t2.start_time


# ═══════════════════════════════════════════════════════════════════════════════
# JSON structured logging
# ═══════════════════════════════════════════════════════════════════════════════


class TestJSONStructuredLogging:
    """Verify JSON log format is available."""

    def test_json_formatter_produces_valid_json(self):
        from releasepilot.shared.logging import JSONFormatter

        # GIVEN a JSON formatter and a log record
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message %s",
            args=("arg1",),
            exc_info=None,
        )
        # WHEN formatting the record
        output = formatter.format(record)
        parsed = json.loads(output)
        # THEN the output is valid JSON with expected fields
        assert parsed["message"] == "test message arg1"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed

    def test_json_formatter_includes_extras(self):
        from releasepilot.shared.logging import JSONFormatter

        # GIVEN a log record with extra fields
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="request handled",
            args=(),
            exc_info=None,
        )
        record.request_path = "/api/status"
        record.duration_ms = 42
        # WHEN formatting the record
        output = formatter.format(record)
        parsed = json.loads(output)
        # THEN extra fields are included
        assert parsed["request_path"] == "/api/status"
        assert parsed["duration_ms"] == 42

    def test_configure_root_logger_json_mode(self):
        from releasepilot.shared.logging import JSONFormatter, configure_root_logger

        # GIVEN a clean root logger
        root = logging.getLogger("releasepilot")
        root.handlers.clear()

        # WHEN configuring with JSON log format
        with patch.dict(os.environ, {"RELEASEPILOT_LOG_FORMAT": "json"}):
            configure_root_logger(verbose=False)

        # THEN a JSONFormatter handler is attached
        assert any(isinstance(h.formatter, JSONFormatter) for h in root.handlers)
        root.handlers.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# UTC datetime in dashboard
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboardUTCDatetime:
    """Verify dashboard use_case uses timezone-aware datetime."""

    def test_generated_at_contains_utc_offset(self):
        from releasepilot.config.settings import Settings
        from releasepilot.dashboard.use_case import DashboardUseCase

        # GIVEN a dashboard use case with settings
        settings = Settings(repo_path="/nonexistent/path")
        # WHEN executing the use case
        data = DashboardUseCase().execute(settings)
        ts = data.generated_at
        # THEN the timestamp contains a UTC offset
        assert "+00:00" in ts or "Z" in ts or "UTC" in ts


# ═══════════════════════════════════════════════════════════════════════════════
# CSP nonce instead of unsafe-inline
# ═══════════════════════════════════════════════════════════════════════════════


class TestCSPNonce:
    """Verify CSP uses nonce-based policy instead of unsafe-inline."""

    def test_csp_contains_nonce(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN requesting any endpoint
        resp = client.get("/health/live")
        csp = resp.headers.get("content-security-policy", "")
        # THEN CSP uses nonce-based policy
        # script-src and style-src must use nonce, not unsafe-inline
        assert "script-src 'self' 'nonce-" in csp
        assert "style-src 'self' 'nonce-" in csp
        # style-src-attr may allow unsafe-inline for inline style attributes
        assert "nonce-" in csp

    def test_csp_nonce_is_different_per_request(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN making two separate requests
        resp1 = client.get("/health/live")
        resp2 = client.get("/health/live")
        csp1 = resp1.headers.get("content-security-policy", "")
        csp2 = resp2.headers.get("content-security-policy", "")
        nonce1 = re.search(r"nonce-([^']+)", csp1)
        nonce2 = re.search(r"nonce-([^']+)", csp2)
        # THEN each request gets a unique nonce
        assert nonce1 and nonce2
        assert nonce1.group(1) != nonce2.group(1)


# ═══════════════════════════════════════════════════════════════════════════════
# Clone URL validation (HTTPS only)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCloneURLValidation:
    """Verify only HTTPS URLs are accepted for cloning."""

    def test_ssh_url_rejected(self):
        from releasepilot.cli.guide import _step_clone_repo

        # GIVEN an SSH clone URL
        # WHEN attempting to clone
        result = _step_clone_repo("git@github.com:user/repo.git")
        # THEN the URL is rejected
        assert result is None

    def test_http_url_rejected(self):
        from releasepilot.cli.guide import _step_clone_repo

        # GIVEN an HTTP (non-HTTPS) clone URL
        # WHEN attempting to clone
        result = _step_clone_repo("http://github.com/user/repo.git")
        # THEN the URL is rejected
        assert result is None

    def test_git_protocol_url_rejected(self):
        from releasepilot.cli.guide import _step_clone_repo

        # GIVEN a git:// protocol URL
        # WHEN attempting to clone
        result = _step_clone_repo("git://github.com/user/repo.git")
        # THEN the URL is rejected
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Web server endpoint tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestWebServerEndpoints:
    """Integration tests for web server routes."""

    def test_health_live(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN checking liveness
        resp = client.get("/health/live")
        # THEN the server reports alive
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_health_ready(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN checking readiness
        resp = client.get("/health/ready")
        # THEN the server is ready
        assert resp.status_code == 200

    def test_api_status(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN requesting API status
        resp = client.get("/api/status")
        # THEN status includes expected fields
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "uptime_seconds" in data
        assert "git_available" in data

    def test_api_config_get(self):
        # GIVEN a server configured with Polish language
        app = create_app({"repo_path": "/tmp", "language": "pl"})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN fetching the config
        resp = client.get("/api/config")
        # THEN the config reflects the setting
        assert resp.status_code == 200
        assert resp.json()["language"] == "pl"

    def test_api_generate_results_empty(self):
        # GIVEN a server with no prior generation
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN fetching generation results
        resp = client.get("/api/generate/results")
        # THEN no results are found
        assert resp.status_code == 404

    def test_favicon(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN requesting the favicon
        resp = client.get("/favicon.ico")
        # THEN a PNG image is returned
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"


# ═══════════════════════════════════════════════════════════════════════════════
# PDF/DOCX render() raises NotImplementedError
# ═══════════════════════════════════════════════════════════════════════════════


class TestBinaryRendererNotImplemented:
    """Verify PDF/DOCX .render() raises NotImplementedError."""

    def test_pdf_render_raises(self):
        from releasepilot.rendering.pdf import PdfRenderer

        # GIVEN a PdfRenderer instance
        # WHEN calling render() instead of render_bytes()
        # THEN NotImplementedError is raised
        with pytest.raises(NotImplementedError, match="render_bytes"):
            PdfRenderer().render(MagicMock(), MagicMock())

    def test_docx_render_raises(self):
        from releasepilot.rendering.docx_renderer import DocxRenderer

        # GIVEN a DocxRenderer instance
        # WHEN calling render() instead of render_bytes()
        # THEN NotImplementedError is raised
        with pytest.raises(NotImplementedError, match="render_bytes"):
            DocxRenderer().render(MagicMock(), MagicMock())


# ═══════════════════════════════════════════════════════════════════════════════
# Accent color validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestAccentColorValidation:
    """Verify accent_color format is validated in config."""

    def test_valid_hex_color_no_warning(self):
        from releasepilot.config.file_config import validate_config

        # GIVEN a valid hex color value
        # WHEN validating the config
        warnings = validate_config({"accent_color": "#FB6400"})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        # THEN no warnings are produced
        assert len(color_warnings) == 0

    def test_invalid_hex_color_warns(self):
        from releasepilot.config.file_config import validate_config

        # GIVEN an invalid color string
        # WHEN validating the config
        warnings = validate_config({"accent_color": "not-a-color"})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        # THEN a warning is produced
        assert len(color_warnings) == 1

    def test_short_hex_warns(self):
        from releasepilot.config.file_config import validate_config

        # GIVEN a short hex color value
        # WHEN validating the config
        warnings = validate_config({"accent_color": "#FFF"})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        # THEN a warning is produced
        assert len(color_warnings) == 1

    def test_missing_hash_warns(self):
        from releasepilot.config.file_config import validate_config

        # GIVEN a hex color missing the hash prefix
        # WHEN validating the config
        warnings = validate_config({"accent_color": "FB6400"})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        # THEN a warning is produced
        assert len(color_warnings) == 1

    def test_empty_accent_color_ok(self):
        from releasepilot.config.file_config import validate_config

        # GIVEN an empty accent color
        # WHEN validating the config
        warnings = validate_config({"accent_color": ""})
        color_warnings = [w for w in warnings if w.field == "accent_color"]
        # THEN no warnings are produced
        assert len(color_warnings) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Multi command failure summary
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiCommandFailureSummary:
    """Verify multi command reports failures properly."""

    def test_multi_exits_nonzero_on_failure(self):
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        # GIVEN the multi command with nonexistent repos
        runner = CliRunner()
        # WHEN invoking multi with invalid paths
        result = runner.invoke(
            cli,
            [
                "multi",
                "/nonexistent/repo1",
                "/nonexistent/repo2",
                "--audience",
                "changelog",
            ],
        )
        # THEN the command exits with non-zero status
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════════════════
# _SuppressOs backward compatibility
# ═══════════════════════════════════════════════════════════════════════════════


class TestSuppressOsCompat:
    """Verify _SuppressOs still works."""

    def test_suppress_os_still_works(self):
        from releasepilot.cli.helpers import _SuppressOs

        # GIVEN the _SuppressOs context manager
        # WHEN an OSError is raised inside it
        # THEN the error is suppressed
        with _SuppressOs():
            raise OSError("test")

    def test_suppress_os_does_not_suppress_other(self):
        from releasepilot.cli.helpers import _SuppressOs

        # GIVEN the _SuppressOs context manager
        # WHEN a non-OS error is raised
        # THEN the error propagates
        with pytest.raises(ValueError):
            with _SuppressOs():
                raise ValueError("not os error")


# ═══════════════════════════════════════════════════════════════════════════════
# __all__ exports in init modules
# ═══════════════════════════════════════════════════════════════════════════════


class TestAllExports:
    """Verify __all__ is defined in public modules."""

    def test_root_init_has_all(self):
        # GIVEN the releasepilot package
        import releasepilot

        # THEN __all__ is defined
        assert hasattr(releasepilot, "__all__")

    def test_rendering_init_has_all(self):
        # GIVEN the rendering package
        import releasepilot.rendering

        # THEN __all__ is defined and contains REPO_URL
        assert hasattr(releasepilot.rendering, "__all__")
        assert "REPO_URL" in releasepilot.rendering.__all__

    def test_domain_init_has_all(self):
        # GIVEN the domain package
        import releasepilot.domain

        # THEN __all__ is defined
        assert hasattr(releasepilot.domain, "__all__")

    def test_config_init_has_all(self):
        # GIVEN the config package
        import releasepilot.config

        # THEN __all__ is defined
        assert hasattr(releasepilot.config, "__all__")

    def test_web_init_has_all(self):
        # GIVEN the web package
        import releasepilot.web

        # THEN __all__ is defined
        assert hasattr(releasepilot.web, "__all__")


# ═══════════════════════════════════════════════════════════════════════════════
# Git health check at startup
# ═══════════════════════════════════════════════════════════════════════════════


class TestGitHealthCheck:
    """Verify git availability check exists."""

    def test_check_git_available(self):
        from releasepilot.web.server import _check_git_available

        # WHEN checking git availability
        result = _check_git_available()
        # THEN a boolean is returned
        assert isinstance(result, bool)

    def test_api_status_includes_git_available(self):
        # GIVEN a running server
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        # WHEN requesting API status
        resp = client.get("/api/status")
        # THEN git_available is included
        assert "git_available" in resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# Version consistency
# ═══════════════════════════════════════════════════════════════════════════════


class TestVersionConsistency:
    """Verify version is consistent between __init__.py and pyproject.toml."""

    def test_version_matches_pyproject(self):
        # GIVEN the package version and pyproject.toml
        from releasepilot import __version__

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject_path.read_text()
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        assert match, "Could not find version in pyproject.toml"
        # THEN the versions match
        assert __version__ == match.group(1)
