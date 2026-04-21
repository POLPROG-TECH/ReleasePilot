"""Tests for template safety and i18n correctness.

Covers:
- Jinja2 autoescape enabled in dashboard renderer
- Markdown stats table labels translated via get_label()
- asyncio.get_event_loop() replaced in thread callbacks
- Git separators use ASCII control characters
"""

from __future__ import annotations

from pathlib import Path

from releasepilot.domain.models import (
    ReleaseNotes,
    ReleaseRange,
)


def _make_notes(**kw) -> ReleaseNotes:
    defaults = dict(
        release_range=ReleaseRange(from_ref="v1.0", to_ref="HEAD"),
        groups=(),
        highlights=(),
        breaking_changes=(),
        total_changes=0,
    )
    defaults.update(kw)
    return ReleaseNotes(**defaults)


# ══════════════════════════════════════════════════════════════════════════════
# Jinja2 autoescape must be enabled
# ══════════════════════════════════════════════════════════════════════════════


class TestAutoescapeEnabled:
    """Dashboard renderer must have autoescape=True."""

    """GIVEN a scenario for autoescape is enabled"""

    def test_autoescape_is_enabled(self):
        """WHEN the test exercises autoescape is enabled"""
        from releasepilot.dashboard.renderer import DashboardRenderer

        renderer = DashboardRenderer()
        # select_autoescape() returns a callable; verify it's truthy and not False
        """THEN the expected behavior for autoescape is enabled is observed"""
        assert renderer._env.autoescape
        assert renderer._env.autoescape is not False

    """GIVEN Pre-escaped JSON with |safe should not be double-escaped"""

    def test_safe_json_not_double_escaped(self):
        """WHEN the test exercises safe json not double escaped"""
        from releasepilot.dashboard.renderer import DashboardRenderer

        renderer = DashboardRenderer()
        template = renderer._env.from_string("var D = {{ data|safe }};")
        json_str = '{"key":"value"}'
        result = template.render(data=json_str)
        """THEN the expected behavior for safe json not double escaped is observed"""
        assert result == 'var D = {"key":"value"};'

    """GIVEN Plain strings without |safe must be auto-escaped"""

    def test_plain_string_is_escaped(self):
        """WHEN the test exercises plain string is escaped"""
        from releasepilot.dashboard.renderer import DashboardRenderer

        renderer = DashboardRenderer()
        template = renderer._env.from_string("<p>{{ text }}</p>")
        result = template.render(text="<script>alert(1)</script>")
        """THEN the expected behavior for plain string is escaped is observed"""
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    """GIVEN Source code must not contain autoescape=False"""

    def test_source_has_no_autoescape_false(self):
        """WHEN the test exercises source has no autoescape false"""
        src = Path(__file__).resolve().parent.parent / ("src/releasepilot/dashboard/renderer.py")
        source = src.read_text()
        """THEN the expected behavior for source has no autoescape false is observed"""
        assert "autoescape=False" not in source


# ══════════════════════════════════════════════════════════════════════════════
# Stats table labels translated via i18n
# ══════════════════════════════════════════════════════════════════════════════


class TestStatsLabelsI18n:
    """Stats block metric labels must use get_label() for i18n."""

    """GIVEN When language is 'pl', stats block should contain Polish labels"""

    def test_stats_labels_translated_polish(self):
        """WHEN the test exercises stats labels translated polish"""
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes(
            total_changes=10,
            metadata={
                "raw_count": "20",
                "filtered_out": "5",
                "first_commit_date": "2025-01-01",
                "last_commit_date": "2025-06-01",
                "effective_branch": "main",
                "components": "api, web",
            },
        )
        config = RenderConfig(language="pl")
        result = MarkdownRenderer().render(notes, config)
        # Polish labels must appear, not English
        """THEN the expected behavior for stats labels translated polish is observed"""
        assert "Surowe zmiany" in result
        assert "Odfiltrowane" in result
        assert "Pierwszy commit" in result
        assert "Ostatni commit" in result
        assert "Gałąź" in result
        assert "Komponenty" in result
        # English labels must NOT appear
        assert "| Raw changes" not in result
        assert "| Filtered out" not in result
        assert "| First commit" not in result

    """GIVEN English locale renders English labels"""

    def test_stats_labels_english(self):
        """WHEN the test exercises stats labels english"""
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.markdown import MarkdownRenderer

        notes = _make_notes(
            total_changes=10,
            metadata={
                "raw_count": "20",
                "filtered_out": "3",
                "effective_branch": "develop",
            },
        )
        config = RenderConfig(language="en")
        result = MarkdownRenderer().render(notes, config)
        """THEN the expected behavior for stats labels english is observed"""
        assert "Raw changes" in result
        assert "Filtered out" in result
        assert "Branch" in result

    """GIVEN All stats label keys must be present in the i18n catalog"""

    def test_i18n_keys_exist_for_stats_labels(self):
        """WHEN the test exercises i18n keys exist for stats labels"""
        from releasepilot.i18n.labels import _LABELS

        required = [
            "raw_changes",
            "filtered_out",
            "deduplicated",
            "final_changes",
            "first_commit",
            "last_commit",
            "branch",
            "components",
            "contributors",
        ]
        for key in required:
            assert key in _LABELS, f"Missing i18n key: {key}"
            assert "en" in _LABELS[key]
            assert "pl" in _LABELS[key]

    """GIVEN The _render_stats_block source must not contain hardcoded metric labels"""

    def test_no_hardcoded_english_in_stats_block(self):
        """WHEN the test exercises no hardcoded english in stats block"""
        src = Path(__file__).resolve().parent.parent / ("src/releasepilot/rendering/markdown.py")
        source = src.read_text()
        # Extract just the _render_stats_block function body
        for hardcoded in [
            "| Raw changes",
            "| Filtered out",
            "| First commit",
            "| Last commit",
            "| Branch |",
            "| Components |",
            "| Contributors |",
        ]:
            assert hardcoded not in source, f"Hardcoded label found: {hardcoded}"


# ══════════════════════════════════════════════════════════════════════════════
# asyncio.get_event_loop() must not be used in thread callbacks
# ══════════════════════════════════════════════════════════════════════════════


class TestAsyncioEventLoopSafety:
    """Thread callbacks must not use deprecated asyncio.get_event_loop()."""

    """GIVEN server.py must use get_running_loop() instead of get_event_loop()"""

    def test_no_get_event_loop_in_server(self):
        """WHEN the test exercises no get event loop in server"""
        src = Path(__file__).resolve().parent.parent / ("src/releasepilot/web/server.py")
        source = src.read_text()
        """THEN the expected behavior for no get event loop in server is observed"""
        assert "get_event_loop()" not in source
        assert "get_running_loop()" in source


# ══════════════════════════════════════════════════════════════════════════════
# Git separators use ASCII control characters
# ══════════════════════════════════════════════════════════════════════════════


class TestAsciiSeparators:
    """Git log delimiters must be ASCII control characters."""

    """GIVEN a scenario for field sep is unit separator"""

    def test_field_sep_is_unit_separator(self):
        """WHEN the test exercises field sep is unit separator"""
        from releasepilot.sources.git import _FIELD_SEP

        """THEN the expected behavior for field sep is unit separator is observed"""
        assert _FIELD_SEP == "\x1f"
        assert ord(_FIELD_SEP) == 31

    """GIVEN a scenario for record sep is record separator"""

    def test_record_sep_is_record_separator(self):
        """WHEN the test exercises record sep is record separator"""
        from releasepilot.sources.git import _RECORD_SEP

        """THEN the expected behavior for record sep is record separator is observed"""
        assert _RECORD_SEP == "\x1e"
        assert ord(_RECORD_SEP) == 30

    """GIVEN Source must not contain the old Unicode delimiters"""

    def test_no_unicode_separators_in_source(self):
        """WHEN the test exercises no unicode separators in source"""
        src = Path(__file__).resolve().parent.parent / ("src/releasepilot/sources/git.py")
        source = src.read_text()
        """THEN the expected behavior for no unicode separators in source is observed"""
        assert "§§§" not in source
        assert "∞∞∞" not in source

    """GIVEN _parse_log must work with the new ASCII separators"""

    def test_parse_log_with_ascii_separators(self):
        """WHEN the test exercises parse log with ascii separators"""
        from releasepilot.sources.git import _FIELD_SEP, _RECORD_SEP, GitSourceCollector

        collector = GitSourceCollector(".")
        record = (
            _FIELD_SEP.join(
                [
                    "b" * 40,
                    "Bob",
                    "2025-03-15T10:00:00Z",
                    "fix: login bug",
                    "Detailed fix description",
                ]
            )
            + _RECORD_SEP
        )

        items = collector._parse_log(record)
        """THEN the expected behavior for parse log with ascii separators is observed"""
        assert len(items) == 1
        assert items[0].title == "fix: login bug"
        assert items[0].authors == ("Bob",)
        assert items[0].description == "Detailed fix description"
