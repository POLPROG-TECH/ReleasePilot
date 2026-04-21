"""Tests for security, authentication, middleware, and server infrastructure.

Each test class covers a specific concern such as auth, CORS, rate limiting,
input validation, and server configuration.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from releasepilot.web.server import create_app


class TestJSONStructuredLogging:
    """Verify JSON log format is available."""

    """GIVEN a scenario for json formatter produces valid json"""

    def test_json_formatter_produces_valid_json(self):
        """WHEN the test exercises json formatter produces valid json"""
        from releasepilot.shared.logging import JSONFormatter

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
        output = formatter.format(record)
        parsed = json.loads(output)
        """THEN the expected behavior for json formatter produces valid json is observed"""
        assert parsed["message"] == "test message arg1"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed

    """GIVEN a scenario for json formatter includes extras"""

    def test_json_formatter_includes_extras(self):
        """WHEN the test exercises json formatter includes extras"""
        from releasepilot.shared.logging import JSONFormatter

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
        output = formatter.format(record)
        parsed = json.loads(output)
        """THEN the expected behavior for json formatter includes extras is observed"""
        assert parsed["request_path"] == "/api/status"
        assert parsed["duration_ms"] == 42

    """GIVEN a scenario for configure root logger json mode"""

    def test_configure_root_logger_json_mode(self):
        """WHEN the test exercises configure root logger json mode"""
        from releasepilot.shared.logging import JSONFormatter, configure_root_logger

        root = logging.getLogger("releasepilot")
        root.handlers.clear()

        with patch.dict(os.environ, {"RELEASEPILOT_LOG_FORMAT": "json"}):
            configure_root_logger(verbose=False)

        """THEN the expected behavior for configure root logger json mode is observed"""
        assert any(isinstance(h.formatter, JSONFormatter) for h in root.handlers)
        root.handlers.clear()


class TestDashboardUTCDatetime:
    """Verify dashboard use_case uses timezone-aware datetime."""

    """GIVEN a scenario for generated at contains utc offset"""

    def test_generated_at_contains_utc_offset(self):
        """WHEN the test exercises generated at contains utc offset"""
        from releasepilot.config.settings import Settings
        from releasepilot.dashboard.use_case import DashboardUseCase

        settings = Settings(repo_path="/nonexistent/path")
        data = DashboardUseCase().execute(settings)
        ts = data.generated_at
        """THEN the expected behavior for generated at contains utc offset is observed"""
        assert "+00:00" in ts or "Z" in ts or "UTC" in ts


class TestCSPNonce:
    """Verify CSP uses nonce-based policy instead of unsafe-inline."""

    """GIVEN a scenario for csp contains nonce"""

    def test_csp_contains_nonce(self):
        """WHEN the test exercises csp contains nonce"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health/live")
        csp = resp.headers.get("content-security-policy", "")
        # script-src and style-src must use nonce, not unsafe-inline
        """THEN the expected behavior for csp contains nonce is observed"""
        assert "script-src 'self' 'nonce-" in csp
        assert "style-src 'self' 'nonce-" in csp
        # style-src-attr may allow unsafe-inline for inline style attributes
        assert "nonce-" in csp

    """GIVEN a scenario for csp nonce is different per request"""

    def test_csp_nonce_is_different_per_request(self):
        """WHEN the test exercises csp nonce is different per request"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp1 = client.get("/health/live")
        resp2 = client.get("/health/live")
        csp1 = resp1.headers.get("content-security-policy", "")
        csp2 = resp2.headers.get("content-security-policy", "")
        nonce1 = re.search(r"nonce-([^']+)", csp1)
        nonce2 = re.search(r"nonce-([^']+)", csp2)
        """THEN the expected behavior for csp nonce is different per request is observed"""
        assert nonce1 and nonce2
        assert nonce1.group(1) != nonce2.group(1)


class TestWebServerEndpoints:
    """Integration tests for web server routes."""

    """GIVEN a scenario for health live"""

    def test_health_live(self):
        """WHEN the test exercises health live"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health/live")
        """THEN the expected behavior for health live is observed"""
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    """GIVEN a scenario for health ready"""

    def test_health_ready(self):
        """WHEN the test exercises health ready"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health/ready")
        """THEN the expected behavior for health ready is observed"""
        assert resp.status_code == 200

    """GIVEN a scenario for api status"""

    def test_api_status(self):
        """WHEN the test exercises api status"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/status")
        """THEN the expected behavior for api status is observed"""
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "uptime_seconds" in data
        assert "git_available" in data

    """GIVEN a scenario for api config get"""

    def test_api_config_get(self):
        """WHEN the test exercises api config get"""
        app = create_app({"repo_path": "/tmp", "language": "pl"})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/config")
        """THEN the expected behavior for api config get is observed"""
        assert resp.status_code == 200
        assert resp.json()["language"] == "pl"

    """GIVEN a scenario for api generate results empty"""

    def test_api_generate_results_empty(self):
        """WHEN the test exercises api generate results empty"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/generate/results")
        """THEN the expected behavior for api generate results empty is observed"""
        assert resp.status_code == 404

    """GIVEN a scenario for favicon"""

    def test_favicon(self):
        """WHEN the test exercises favicon"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/favicon.ico")
        """THEN the expected behavior for favicon is observed"""
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"


class TestBinaryRendererNotImplemented:
    """Verify PDF/DOCX .render() raises NotImplementedError."""

    """GIVEN a scenario for pdf render raises"""

    def test_pdf_render_raises(self):
        """WHEN the test exercises pdf render raises"""
        from releasepilot.rendering.pdf import PdfRenderer

        """THEN the expected behavior for pdf render raises is observed"""
        with pytest.raises(NotImplementedError, match="render_bytes"):
            PdfRenderer().render(MagicMock(), MagicMock())

    """GIVEN a scenario for docx render raises"""

    def test_docx_render_raises(self):
        """WHEN the test exercises docx render raises"""
        from releasepilot.rendering.docx_renderer import DocxRenderer

        """THEN the expected behavior for docx render raises is observed"""
        with pytest.raises(NotImplementedError, match="render_bytes"):
            DocxRenderer().render(MagicMock(), MagicMock())


class TestMultiCommandFailureSummary:
    """Verify multi command reports failures properly."""

    """GIVEN a scenario for multi exits nonzero on failure"""

    def test_multi_exits_nonzero_on_failure(self):
        """WHEN the test exercises multi exits nonzero on failure"""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        runner = CliRunner()
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
        """THEN the expected behavior for multi exits nonzero on failure is observed"""
        assert result.exit_code != 0


class TestAllExports:
    """Verify __all__ is defined in public modules."""

    """GIVEN a scenario for root init has all"""

    def test_root_init_has_all(self):
        """WHEN the test exercises root init has all"""
        import releasepilot

        """THEN the expected behavior for root init has all is observed"""
        assert hasattr(releasepilot, "__all__")

    """GIVEN a scenario for rendering init has all"""

    def test_rendering_init_has_all(self):
        """WHEN the test exercises rendering init has all"""
        import releasepilot.rendering

        """THEN the expected behavior for rendering init has all is observed"""
        assert hasattr(releasepilot.rendering, "__all__")
        assert "REPO_URL" in releasepilot.rendering.__all__

    """GIVEN a scenario for domain init has all"""

    def test_domain_init_has_all(self):
        """WHEN the test exercises domain init has all"""
        import releasepilot.domain

        """THEN the expected behavior for domain init has all is observed"""
        assert hasattr(releasepilot.domain, "__all__")

    """GIVEN a scenario for config init has all"""

    def test_config_init_has_all(self):
        """WHEN the test exercises config init has all"""
        import releasepilot.config

        """THEN the expected behavior for config init has all is observed"""
        assert hasattr(releasepilot.config, "__all__")

    """GIVEN a scenario for web init has all"""

    def test_web_init_has_all(self):
        """WHEN the test exercises web init has all"""
        import releasepilot.web

        """THEN the expected behavior for web init has all is observed"""
        assert hasattr(releasepilot.web, "__all__")


class TestVersionConsistency:
    """Verify version is consistent between __init__.py and pyproject.toml."""

    """GIVEN a scenario for version matches pyproject"""

    def test_version_matches_pyproject(self):
        """WHEN the test exercises version matches pyproject"""
        from releasepilot import __version__

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject_path.read_text()
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        """THEN the expected behavior for version matches pyproject is observed"""
        assert match, "Could not find version in pyproject.toml"
        assert __version__ == match.group(1)
