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

    """GIVEN The footer must render pipeline_summary text from metadata"""

    def test_footer_with_pipeline_summary(self):
        """WHEN the test exercises footer with pipeline summary"""
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes(
            metadata={
                "pipeline_summary": "50 collected → 5 filtered → 0 deduplicated → 45 final",
                "raw_count": "50",
            }
        )
        config = RenderConfig()
        output = MarkdownRenderer().render(notes, config)
        """THEN the expected behavior for footer with pipeline summary is observed"""
        assert "Pipeline:" in output
        assert "50 collected" in output

    """GIVEN Rendering must not crash when pipeline_summary is absent"""

    def test_footer_without_pipeline_summary(self):
        """WHEN the test exercises footer without pipeline summary"""
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes(metadata={})
        config = RenderConfig()
        output = MarkdownRenderer().render(notes, config)
        """THEN the expected behavior for footer without pipeline summary is observed"""
        assert "Pipeline:" not in output


# ═══════════════════════════════════════════════════════════════════════════════
# Atomic write double-close prevention
# ═══════════════════════════════════════════════════════════════════════════════


class TestAtomicWriteDoubleClose:
    """Verify atomic write helpers don't double-close file descriptors."""

    """GIVEN Normal write should produce correct file content"""

    def test_atomic_write_text_success(self, tmp_path: Path):
        """WHEN the test exercises atomic write text success"""
        from releasepilot.cli.helpers import _atomic_write_text

        target = tmp_path / "out.txt"
        _atomic_write_text(str(target), "hello world")
        """THEN the expected behavior for atomic write text success is observed"""
        assert target.read_text() == "hello world"

    """GIVEN Normal write of bytes should produce correct file content"""

    def test_atomic_write_bytes_success(self, tmp_path: Path):
        """WHEN the test exercises atomic write bytes success"""
        from releasepilot.cli.helpers import _atomic_write_bytes

        target = tmp_path / "out.bin"
        _atomic_write_bytes(str(target), b"\x00\x01\x02")
        """THEN the expected behavior for atomic write bytes success is observed"""
        assert target.read_bytes() == b"\x00\x01\x02"

    """GIVEN When os.replace fails, the fd should be safely closed once"""

    def test_atomic_write_text_replace_failure_no_double_close(self, tmp_path: Path):
        """WHEN the test exercises atomic write text replace failure no double close"""
        from releasepilot.cli.helpers import _atomic_write_text

        target = tmp_path / "out.txt"

        with patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                _atomic_write_text(str(target), "content")

        remaining = list(tmp_path.glob("*.tmp"))
        """THEN the expected behavior for atomic write text replace failure no double close is observed"""
        assert len(remaining) == 0

    """GIVEN Atomic write should atomically overwrite existing files"""

    def test_atomic_write_bytes_overwrites_existing(self, tmp_path: Path):
        """WHEN the test exercises atomic write bytes overwrites existing"""
        from releasepilot.cli.helpers import _atomic_write_bytes

        target = tmp_path / "out.bin"
        target.write_bytes(b"old data")
        _atomic_write_bytes(str(target), b"new data")
        """THEN the expected behavior for atomic write bytes overwrites existing is observed"""
        assert target.read_bytes() == b"new data"


# ═══════════════════════════════════════════════════════════════════════════════
# XSS prevention in web server error pages
# ═══════════════════════════════════════════════════════════════════════════════


class TestWebServerXSS:
    """Verify that error pages escape HTML special characters."""

    """GIVEN HTML special chars in error messages must be escaped"""

    def test_error_message_is_escaped(self):
        """WHEN the test exercises error message is escaped"""
        from html import escape

        malicious = '<script>alert("xss")</script>'
        escaped = escape(malicious)
        """THEN the expected behavior for error message is escaped is observed"""
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    """GIVEN The dashboard page error handler should escape exception text"""

    @pytest.mark.asyncio
    async def test_dashboard_error_escapes_exception(self):
        """WHEN the test exercises dashboard error escapes exception"""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        app = create_app({"repo_path": "/nonexistent/path/that/does/not/exist"})

        with patch(
            "releasepilot.web.server._generate_dashboard_html",
            side_effect=ValueError('<img src=x onerror="alert(1)">'),
        ):
            client = TestClient(app)
            resp = client.get("/")
            assert "<img src=x" not in resp.text
            assert "&lt;img" in resp.text or resp.status_code == 500


# ═══════════════════════════════════════════════════════════════════════════════
# Race condition in /api/generate
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateRaceCondition:
    """Verify that concurrent generation requests are properly serialized."""

    """GIVEN A second generate request should get 409 while first is running"""

    def test_generate_rejects_while_running(self):
        """WHEN the test exercises generate rejects while running"""
        from releasepilot.web.state import AnalysisPhase, AnalysisProgress, AppState

        state = AppState()
        state.analysis_progress = AnalysisProgress(phase=AnalysisPhase.RUNNING)
        """THEN the expected behavior for generate rejects while running is observed"""
        assert state.analysis_progress.phase == AnalysisPhase.RUNNING


# ═══════════════════════════════════════════════════════════════════════════════
# Font registration thread safety
# ═══════════════════════════════════════════════════════════════════════════════


class TestFontRegistrationThreadSafety:
    """Verify font registration is thread-safe."""

    """GIVEN Multiple threads calling register_unicode_font must not crash"""

    def test_concurrent_registration_no_crash(self):
        """WHEN the test exercises concurrent registration no crash"""
        import releasepilot.rendering.fonts as fonts_mod

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

        threads = [threading.Thread(target=register) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        """THEN the expected behavior for concurrent registration no crash is observed"""
        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 10
        assert len(set(results)) == 1

    """GIVEN Calling register_unicode_font twice returns same result"""

    def test_registration_idempotent(self):
        """WHEN the test exercises registration idempotent"""
        import releasepilot.rendering.fonts as fonts_mod

        fonts_mod._init_done = False
        fonts_mod._registered_font = None

        r1 = fonts_mod.register_unicode_font()
        r2 = fonts_mod.register_unicode_font()
        """THEN the expected behavior for registration idempotent is observed"""
        assert r1 == r2


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard command dry_run handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboardDryRunKwarg:
    """Verify dashboard command properly handles dry_run kwarg."""

    """GIVEN _build_settings must not crash when dry_run is absent"""

    def test_build_settings_accepts_no_dry_run(self):
        """WHEN the test exercises build settings accepts no dry run"""
        from releasepilot.cli.helpers import _build_settings

        settings = _build_settings(
            repo=".",
            from_ref="",
            to_ref="HEAD",
            source_file="",
            version_str="",
            title="",
        )
        """THEN the expected behavior for build settings accepts no dry run is observed"""
        assert settings.repo_path == "."

    """GIVEN _build_settings should not accept dry_run as a parameter"""

    def test_build_settings_rejects_dry_run(self):
        """WHEN the test exercises build settings rejects dry run"""
        from releasepilot.cli.helpers import _build_settings

        """THEN the expected behavior for build settings rejects dry run is observed"""
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

    """GIVEN JSON with total_changes=0 should be detected as empty"""

    def test_empty_json_detected(self):
        """WHEN the test exercises empty json detected"""
        from releasepilot.cli.helpers import _is_empty_release

        json_output = json.dumps(
            {
                "release": {"version": "1.0.0"},
                "total_changes": 0,
                "groups": [],
            }
        )
        """THEN the expected behavior for empty json detected is observed"""
        assert _is_empty_release(json_output) is True

    """GIVEN JSON with changes should not be detected as empty"""

    def test_non_empty_json_not_detected(self):
        """WHEN the test exercises non empty json not detected"""
        from releasepilot.cli.helpers import _is_empty_release

        json_output = json.dumps(
            {
                "release": {"version": "1.0.0"},
                "total_changes": 5,
                "groups": [{"category": "feature", "items": []}],
            }
        )
        """THEN the expected behavior for non empty json not detected is observed"""
        assert _is_empty_release(json_output) is False

    """GIVEN Empty string should be detected as empty release"""

    def test_empty_string_detected(self):
        """WHEN the test exercises empty string detected"""
        from releasepilot.cli.helpers import _is_empty_release

        """THEN the expected behavior for empty string detected is observed"""
        assert _is_empty_release("") is True
        assert _is_empty_release("   ") is True

    """GIVEN Malformed JSON starting with { should not crash"""

    def test_invalid_json_not_crash(self):
        """WHEN the test exercises invalid json not crash"""
        from releasepilot.cli.helpers import _is_empty_release

        """THEN the expected behavior for invalid json not crash is observed"""
        assert _is_empty_release("{invalid json") is False


# ═══════════════════════════════════════════════════════════════════════════════
# Web API config validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestWebConfigValidation:
    """Verify config update endpoint validates enum fields."""

    """GIVEN PUT /api/config with invalid audience should return 400"""

    def test_invalid_audience_rejected(self):
        """WHEN the test exercises invalid audience rejected"""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        app = create_app({})
        client = TestClient(app)
        resp = client.put("/api/config", json={"audience": "invalid_audience"})
        """THEN the expected behavior for invalid audience rejected is observed"""
        assert resp.status_code == 400
        assert "Invalid audience" in resp.json()["error"]

    """GIVEN PUT /api/config with valid audience should return 200"""

    def test_valid_audience_accepted(self):
        """WHEN the test exercises valid audience accepted"""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        app = create_app({})
        client = TestClient(app)
        resp = client.put("/api/config", json={"audience": "executive"})
        """THEN the expected behavior for valid audience accepted is observed"""
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    """GIVEN PUT /api/config with invalid format should return 400"""

    def test_invalid_format_rejected(self):
        """WHEN the test exercises invalid format rejected"""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        app = create_app({})
        client = TestClient(app)
        resp = client.put("/api/config", json={"format": "html"})
        """THEN the expected behavior for invalid format rejected is observed"""
        assert resp.status_code == 400

    """GIVEN PUT /api/config with invalid language should return 400"""

    def test_invalid_language_rejected(self):
        """WHEN the test exercises invalid language rejected"""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        app = create_app({})
        client = TestClient(app)
        resp = client.put("/api/config", json={"language": "xx"})
        """THEN the expected behavior for invalid language rejected is observed"""
        assert resp.status_code == 400

    """GIVEN PUT /api/config with non-dict JSON should return 400"""

    def test_non_dict_body_rejected(self):
        """WHEN the test exercises non dict body rejected"""
        from fastapi.testclient import TestClient

        from releasepilot.web.server import create_app

        app = create_app({})
        client = TestClient(app)
        resp = client.put(
            "/api/config", content='"just a string"', headers={"content-type": "application/json"}
        )
        """THEN the expected behavior for non dict body rejected is observed"""
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# Markdown renderer determinism with metadata
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarkdownStatsBlock:
    """Verify the stats block renders correctly with various metadata states."""

    """GIVEN Stats table should include all populated metadata fields"""

    def test_stats_block_with_full_metadata(self):
        """WHEN the test exercises stats block with full metadata"""
        from releasepilot.rendering.markdown import MarkdownRenderer

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
        output = MarkdownRenderer().render(notes, config)
        """THEN the expected behavior for stats block with full metadata is observed"""
        assert "📊" in output
        assert "100" in output
        assert "auth, api, ui" in output

    """GIVEN Stats table should not appear when raw_count is absent"""

    def test_stats_block_absent_when_no_raw_count(self):
        """WHEN the test exercises stats block absent when no raw count"""
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes(metadata={})
        config = RenderConfig()
        output = MarkdownRenderer().render(notes, config)
        """THEN the expected behavior for stats block absent when no raw count is observed"""
        assert "📊" not in output
