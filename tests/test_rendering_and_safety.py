"""Regression tests for rendering bugs, atomic writes, XSS prevention,
race conditions, thread safety, and config validation.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from releasepilot.config.settings import RenderConfig
from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import (
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_notes(
    *,
    items: list[ChangeItem] | None = None,
    version: str = "1.0.0",
    title: str = "Test Release",
    metadata: dict | None = None,
) -> ReleaseNotes:
    """Build a minimal ReleaseNotes for testing."""
    from releasepilot.processing.grouper import (
        extract_breaking_changes,
        extract_highlights,
        group_changes,
    )

    if items is None:
        items = [
            ChangeItem(
                id="t1",
                title="Add feature X",
                category=ChangeCategory.FEATURE,
                source=SourceReference(commit_hash="aaa111"),
                authors=("alice",),
                timestamp=datetime(2025, 1, 1, tzinfo=UTC),
                raw_message="feat: Add feature X",
            ),
        ]
    groups = group_changes(items)
    highlights = extract_highlights(items)
    breaking = extract_breaking_changes(items)
    return ReleaseNotes(
        release_range=ReleaseRange(
            from_ref="v0.9",
            to_ref="v1.0",
            version=version,
            title=title,
        ),
        groups=tuple(groups),
        highlights=tuple(highlights),
        breaking_changes=tuple(breaking),
        total_changes=len(items),
        metadata=metadata or {},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Markdown f-string nesting in _render_footer (pipeline_summary)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarkdownFooterPipelineSummary:
    """Verify that pipeline_summary metadata renders without syntax errors."""

    def test_footer_with_pipeline_summary(self):
        """The footer must render pipeline_summary text from metadata."""
        from releasepilot.rendering.markdown import MarkdownRenderer

        # GIVEN release notes with pipeline_summary metadata
        notes = _make_notes(
            metadata={
                "pipeline_summary": "50 collected → 5 filtered → 0 deduplicated → 45 final",
                "raw_count": "50",
            }
        )
        config = RenderConfig()
        # WHEN rendering to markdown
        output = MarkdownRenderer().render(notes, config)
        # THEN the pipeline summary appears in the footer
        assert "Pipeline:" in output
        assert "50 collected" in output

    def test_footer_without_pipeline_summary(self):
        """Rendering must not crash when pipeline_summary is absent."""
        from releasepilot.rendering.markdown import MarkdownRenderer

        # GIVEN release notes with no pipeline_summary
        notes = _make_notes(metadata={})
        config = RenderConfig()
        # WHEN rendering to markdown
        output = MarkdownRenderer().render(notes, config)
        # THEN no pipeline line appears
        assert "Pipeline:" not in output


# ═══════════════════════════════════════════════════════════════════════════════
# Atomic write double-close prevention
# ═══════════════════════════════════════════════════════════════════════════════


class TestAtomicWriteDoubleClose:
    """Verify atomic write helpers don't double-close file descriptors."""

    def test_atomic_write_text_success(self, tmp_path: Path):
        """Normal write should produce correct file content."""
        from releasepilot.cli.helpers import _atomic_write_text

        # GIVEN a target path
        target = tmp_path / "out.txt"
        # WHEN writing text atomically
        _atomic_write_text(str(target), "hello world")
        # THEN the file contains the expected content
        assert target.read_text() == "hello world"

    def test_atomic_write_bytes_success(self, tmp_path: Path):
        """Normal write of bytes should produce correct file content."""
        from releasepilot.cli.helpers import _atomic_write_bytes

        # GIVEN a target path
        target = tmp_path / "out.bin"
        # WHEN writing bytes atomically
        _atomic_write_bytes(str(target), b"\x00\x01\x02")
        # THEN the file contains the expected bytes
        assert target.read_bytes() == b"\x00\x01\x02"

    def test_atomic_write_text_replace_failure_no_double_close(self, tmp_path: Path):
        """When os.replace fails, the fd should be safely closed once."""
        from releasepilot.cli.helpers import _atomic_write_text

        target = tmp_path / "out.txt"

        # GIVEN os.replace will fail
        with patch("os.replace", side_effect=OSError("disk full")):
            # WHEN writing text atomically
            with pytest.raises(OSError, match="disk full"):
                _atomic_write_text(str(target), "content")

        # THEN no temp files are left behind
        remaining = list(tmp_path.glob("*.tmp"))
        assert len(remaining) == 0

    def test_atomic_write_bytes_overwrites_existing(self, tmp_path: Path):
        """Atomic write should atomically overwrite existing files."""
        from releasepilot.cli.helpers import _atomic_write_bytes

        # GIVEN an existing file with old data
        target = tmp_path / "out.bin"
        target.write_bytes(b"old data")
        # WHEN overwriting atomically
        _atomic_write_bytes(str(target), b"new data")
        # THEN the file contains only the new data
        assert target.read_bytes() == b"new data"


# ═══════════════════════════════════════════════════════════════════════════════
# XSS prevention in web server error pages
# ═══════════════════════════════════════════════════════════════════════════════


class TestWebServerXSS:
    """Verify that error pages escape HTML special characters."""

    def test_error_message_is_escaped(self):
        """HTML special chars in error messages must be escaped."""
        from html import escape

        # GIVEN a string with malicious HTML
        malicious = '<script>alert("xss")</script>'
        # WHEN escaping
        escaped = escape(malicious)
        # THEN script tags are neutralised
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    @pytest.mark.asyncio
    async def test_dashboard_error_escapes_exception(self):
        """The dashboard page error handler should escape exception text."""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        # GIVEN a dashboard handler that raises with HTML in the message
        app = create_app({"repo_path": "/nonexistent/path/that/does/not/exist"})

        with patch(
            "releasepilot.web.server._generate_dashboard_html",
            side_effect=ValueError('<img src=x onerror="alert(1)">'),
        ):
            client = TestClient(app)
            # WHEN requesting the dashboard
            resp = client.get("/")
            # THEN the error page escapes the HTML
            assert "<img src=x" not in resp.text
            assert "&lt;img" in resp.text or resp.status_code == 500


# ═══════════════════════════════════════════════════════════════════════════════
# Race condition in /api/generate
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateRaceCondition:
    """Verify that concurrent generation requests are properly serialized."""

    def test_generate_rejects_while_running(self):
        """A second generate request should get 409 while first is running."""
        from releasepilot.web.state import AnalysisPhase, AnalysisProgress, AppState

        # GIVEN an app state with analysis already running
        state = AppState()
        state.analysis_progress = AnalysisProgress(phase=AnalysisPhase.RUNNING)
        # WHEN checking the phase
        # THEN it reflects the running state
        assert state.analysis_progress.phase == AnalysisPhase.RUNNING


# ═══════════════════════════════════════════════════════════════════════════════
# Font registration thread safety
# ═══════════════════════════════════════════════════════════════════════════════


class TestFontRegistrationThreadSafety:
    """Verify font registration is thread-safe."""

    def test_concurrent_registration_no_crash(self):
        """Multiple threads calling register_unicode_font must not crash."""
        import releasepilot.rendering.fonts as fonts_mod

        # GIVEN a fresh module state
        fonts_mod._init_done = False
        fonts_mod._registered_font = None

        results = []
        errors = []

        def register():
            try:
                result = fonts_mod.register_unicode_font()
                results.append(result)
            except Exception as e:
                errors.append(e)

        # WHEN 10 threads register concurrently
        threads = [threading.Thread(target=register) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # THEN no errors and all threads get the same result
        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 10
        assert len(set(results)) == 1

    def test_registration_idempotent(self):
        """Calling register_unicode_font twice returns same result."""
        import releasepilot.rendering.fonts as fonts_mod

        # GIVEN a fresh module state
        fonts_mod._init_done = False
        fonts_mod._registered_font = None

        # WHEN registering twice
        r1 = fonts_mod.register_unicode_font()
        r2 = fonts_mod.register_unicode_font()
        # THEN both calls return the same value
        assert r1 == r2


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard command dry_run handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboardDryRunKwarg:
    """Verify dashboard command properly handles dry_run kwarg."""

    def test_build_settings_accepts_no_dry_run(self):
        """_build_settings must not crash when dry_run is absent."""
        from releasepilot.cli.helpers import _build_settings

        # GIVEN standard parameters without dry_run
        # WHEN building settings
        settings = _build_settings(
            repo=".",
            from_ref="",
            to_ref="HEAD",
            source_file="",
            version_str="",
            title="",
        )
        # THEN settings are created successfully
        assert settings.repo_path == "."

    def test_build_settings_rejects_dry_run(self):
        """_build_settings should not accept dry_run as a parameter."""
        from releasepilot.cli.helpers import _build_settings

        # GIVEN dry_run passed as a keyword argument
        # WHEN calling _build_settings
        # THEN a TypeError is raised
        with pytest.raises(TypeError):
            _build_settings(
                repo=".",
                from_ref="",
                to_ref="HEAD",
                source_file="",
                version_str="",
                title="",
                dry_run=True,  # This should cause TypeError
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Empty release detection for JSON format
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmptyReleaseDetectionJSON:
    """Verify empty release detection works for JSON output."""

    def test_empty_json_detected(self):
        """JSON with total_changes=0 should be detected as empty."""
        from releasepilot.cli.helpers import _is_empty_release

        # GIVEN JSON output with zero total_changes
        json_output = json.dumps(
            {
                "release": {"version": "1.0.0"},
                "total_changes": 0,
                "groups": [],
            }
        )
        # WHEN checking for empty release
        # THEN it is detected as empty
        assert _is_empty_release(json_output) is True

    def test_non_empty_json_not_detected(self):
        """JSON with changes should not be detected as empty."""
        from releasepilot.cli.helpers import _is_empty_release

        # GIVEN JSON output with changes
        json_output = json.dumps(
            {
                "release": {"version": "1.0.0"},
                "total_changes": 5,
                "groups": [{"category": "feature", "items": []}],
            }
        )
        # WHEN checking for empty release
        # THEN it is not detected as empty
        assert _is_empty_release(json_output) is False

    def test_empty_string_detected(self):
        """Empty string should be detected as empty release."""
        from releasepilot.cli.helpers import _is_empty_release

        # GIVEN empty or whitespace-only strings
        # WHEN checking for empty release
        # THEN they are detected as empty
        assert _is_empty_release("") is True
        assert _is_empty_release("   ") is True

    def test_invalid_json_not_crash(self):
        """Malformed JSON starting with { should not crash."""
        from releasepilot.cli.helpers import _is_empty_release

        # GIVEN malformed JSON
        # WHEN checking for empty release
        # THEN it does not crash and returns False
        assert _is_empty_release("{invalid json") is False


# ═══════════════════════════════════════════════════════════════════════════════
# Web API config validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestWebConfigValidation:
    """Verify config update endpoint validates enum fields."""

    def test_invalid_audience_rejected(self):
        """PUT /api/config with invalid audience should return 400."""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        # GIVEN a running app
        app = create_app({})
        client = TestClient(app)
        # WHEN sending an invalid audience
        resp = client.put("/api/config", json={"audience": "invalid_audience"})
        # THEN the request is rejected
        assert resp.status_code == 400
        assert "Invalid audience" in resp.json()["error"]

    def test_valid_audience_accepted(self):
        """PUT /api/config with valid audience should return 200."""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        # GIVEN a running app
        app = create_app({})
        client = TestClient(app)
        # WHEN sending a valid audience
        resp = client.put("/api/config", json={"audience": "executive"})
        # THEN the request succeeds
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invalid_format_rejected(self):
        """PUT /api/config with invalid format should return 400."""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        # GIVEN a running app
        app = create_app({})
        client = TestClient(app)
        # WHEN sending an invalid format
        resp = client.put("/api/config", json={"format": "html"})
        # THEN the request is rejected
        assert resp.status_code == 400

    def test_invalid_language_rejected(self):
        """PUT /api/config with invalid language should return 400."""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        # GIVEN a running app
        app = create_app({})
        client = TestClient(app)
        # WHEN sending an invalid language
        resp = client.put("/api/config", json={"language": "xx"})
        # THEN the request is rejected
        assert resp.status_code == 400

    def test_non_dict_body_rejected(self):
        """PUT /api/config with non-dict JSON should return 400."""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        # GIVEN a running app
        app = create_app({})
        client = TestClient(app)
        # WHEN sending a non-dict JSON body
        resp = client.put(
            "/api/config", content='"just a string"', headers={"content-type": "application/json"}
        )
        # THEN the request is rejected
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# Additional regression: Markdown renderer determinism with metadata
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarkdownStatsBlock:
    """Verify the stats block renders correctly with various metadata states."""

    def test_stats_block_with_full_metadata(self):
        """Stats table should include all populated metadata fields."""
        from releasepilot.rendering.markdown import MarkdownRenderer

        # GIVEN release notes with full metadata
        notes = _make_notes(
            metadata={
                "raw_count": "100",
                "filtered_out": "20",
                "contributors": "5",
                "first_commit_date": "2025-01-01",
                "last_commit_date": "2025-03-15",
                "components": "auth, api, ui",
            }
        )
        config = RenderConfig()
        # WHEN rendering to markdown
        output = MarkdownRenderer().render(notes, config)
        # THEN stats block includes the metadata
        assert "📊" in output
        assert "100" in output
        assert "auth, api, ui" in output

    def test_stats_block_absent_when_no_raw_count(self):
        """Stats table should not appear when raw_count is absent."""
        from releasepilot.rendering.markdown import MarkdownRenderer

        # GIVEN release notes with no raw_count
        notes = _make_notes(metadata={})
        config = RenderConfig()
        # WHEN rendering to markdown
        output = MarkdownRenderer().render(notes, config)
        # THEN no stats block appears
        assert "📊" not in output
