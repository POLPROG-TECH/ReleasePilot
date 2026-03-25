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

    def test_autoescape_is_enabled(self):
        from releasepilot.dashboard.renderer import DashboardRenderer

        renderer = DashboardRenderer()
        # select_autoescape() returns a callable; verify it's truthy and not False
        assert renderer._env.autoescape
        assert renderer._env.autoescape is not False

    def test_safe_json_not_double_escaped(self):
        """Pre-escaped JSON with |safe should not be double-escaped."""
        from releasepilot.dashboard.renderer import DashboardRenderer

        renderer = DashboardRenderer()
        template = renderer._env.from_string("var D = {{ data|safe }};")
        json_str = '{"key":"value"}'
        result = template.render(data=json_str)
        assert result == 'var D = {"key":"value"};'

    def test_plain_string_is_escaped(self):
        """Plain strings without |safe must be auto-escaped."""
        from releasepilot.dashboard.renderer import DashboardRenderer

        renderer = DashboardRenderer()
        template = renderer._env.from_string("<p>{{ text }}</p>")
        result = template.render(text="<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_source_has_no_autoescape_false(self):
        """Source code must not contain autoescape=False."""
        src = Path(__file__).resolve().parent.parent / ("src/releasepilot/dashboard/renderer.py")
        source = src.read_text()
        assert "autoescape=False" not in source


# ══════════════════════════════════════════════════════════════════════════════
# Stats table labels translated via i18n
# ══════════════════════════════════════════════════════════════════════════════


class TestStatsLabelsI18n:
    """Stats block metric labels must use get_label() for i18n."""

    def test_stats_labels_translated_polish(self):
        """When language is 'pl', stats block should contain Polish labels."""
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

    def test_stats_labels_english(self):
        """English locale renders English labels."""
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
        assert "Raw changes" in result
        assert "Filtered out" in result
        assert "Branch" in result

    def test_i18n_keys_exist_for_stats_labels(self):
        """All stats label keys must be present in the i18n catalog."""
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

    def test_no_hardcoded_english_in_stats_block(self):
        """The _render_stats_block source must not contain hardcoded metric labels."""
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

    def test_no_get_event_loop_in_server(self):
        """server.py must use get_running_loop() instead of get_event_loop()."""
        src = Path(__file__).resolve().parent.parent / ("src/releasepilot/web/server.py")
        source = src.read_text()
        assert "get_event_loop()" not in source
        assert "get_running_loop()" in source


# ══════════════════════════════════════════════════════════════════════════════
# Git separators use ASCII control characters
# ══════════════════════════════════════════════════════════════════════════════


class TestAsciiSeparators:
    """Git log delimiters must be ASCII control characters."""

    def test_field_sep_is_unit_separator(self):
        from releasepilot.sources.git import _FIELD_SEP

        assert _FIELD_SEP == "\x1f"
        assert ord(_FIELD_SEP) == 31

    def test_record_sep_is_record_separator(self):
        from releasepilot.sources.git import _RECORD_SEP

        assert _RECORD_SEP == "\x1e"
        assert ord(_RECORD_SEP) == 30

    def test_no_unicode_separators_in_source(self):
        """Source must not contain the old Unicode delimiters."""
        src = Path(__file__).resolve().parent.parent / ("src/releasepilot/sources/git.py")
        source = src.read_text()
        assert "§§§" not in source
        assert "∞∞∞" not in source

    def test_parse_log_with_ascii_separators(self):
        """_parse_log must work with the new ASCII separators."""
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
        assert len(items) == 1
        assert items[0].title == "fix: login bug"
        assert items[0].authors == ("Bob",)
        assert items[0].description == "Detailed fix description"
