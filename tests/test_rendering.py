"""Tests for renderers — markdown, plaintext, and JSON."""

from __future__ import annotations

import json

from releasepilot.config.settings import RenderConfig
from releasepilot.domain.models import ReleaseNotes, ReleaseRange
from releasepilot.rendering.json_renderer import JsonRenderer
from releasepilot.rendering.markdown import MarkdownRenderer
from releasepilot.rendering.plaintext import PlaintextRenderer


class TestMarkdownRenderer:
    """Scenarios for MarkdownRenderer."""

    def test_header_contains_title(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes with a title."""
        renderer = MarkdownRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, default_render_config)

        """THEN the title appears as an H1."""
        assert "# Release 1.1.0" in output

    def test_breaking_changes_section(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes with breaking changes."""
        renderer = MarkdownRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, default_render_config)

        """THEN a breaking changes section exists."""
        assert "⚠️ Breaking Changes" in output

    def test_groups_as_h2(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes with multiple groups."""
        renderer = MarkdownRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, default_render_config)

        """THEN each group has an H2 heading."""
        assert "## ✨ New Features" in output
        assert "## 🐛 Bug Fixes" in output

    def test_footer_shows_count(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes."""
        renderer = MarkdownRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, default_render_config)

        """THEN the footer includes the change count."""
        assert "6 changes in this release" in output

    def test_empty_release(self, default_render_config):
        """GIVEN empty release notes."""
        notes = ReleaseNotes(
            release_range=ReleaseRange(from_ref="a", to_ref="b", version="2.0.0"),
            groups=(),
            total_changes=0,
        )
        renderer = MarkdownRenderer()

        """WHEN rendering."""
        output = renderer.render(notes, default_render_config)

        """THEN a polite empty message is shown."""
        assert "No notable changes" in output

    def test_pr_links_shown_by_default(self, sample_notes: ReleaseNotes):
        """GIVEN render config with show_pr_links=True (default)."""
        config = RenderConfig(show_pr_links=True)
        renderer = MarkdownRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, config)

        """THEN PR links are included for items that have them."""
        assert "(#10)" in output

    def test_deterministic_output(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN the same input."""
        renderer = MarkdownRenderer()

        """WHEN rendering twice."""
        output1 = renderer.render(sample_notes, default_render_config)
        output2 = renderer.render(sample_notes, default_render_config)

        """THEN the output is identical."""
        assert output1 == output2


class TestPlaintextRenderer:
    """Scenarios for PlaintextRenderer."""

    def test_header_with_separator(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes."""
        renderer = PlaintextRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, default_render_config)

        """THEN the header has a separator line."""
        lines = output.split("\n")
        assert "Release 1.1.0" in lines[0]
        assert "=" in lines[1]

    def test_bullet_points(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes with items."""
        renderer = PlaintextRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, default_render_config)

        """THEN items are listed with bullets."""
        assert "•" in output

    def test_change_count_in_footer(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes."""
        renderer = PlaintextRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, default_render_config)

        """THEN the count appears."""
        assert "(6 changes)" in output


class TestJsonRenderer:
    """Scenarios for JsonRenderer."""

    def test_valid_json(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes."""
        renderer = JsonRenderer()

        """WHEN rendering."""
        output = renderer.render(sample_notes, default_render_config)

        """THEN the output is valid JSON."""
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_structure_keys(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes."""
        renderer = JsonRenderer()

        """WHEN rendering."""
        data = json.loads(renderer.render(sample_notes, default_render_config))

        """THEN expected top-level keys exist."""
        assert "release" in data
        assert "total_changes" in data
        assert "groups" in data
        assert "highlights" in data
        assert "breaking_changes" in data

    def test_version_in_release(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes with version 1.1.0."""
        renderer = JsonRenderer()

        """WHEN rendering."""
        data = json.loads(renderer.render(sample_notes, default_render_config))

        """THEN the version is in the release object."""
        assert data["release"]["version"] == "1.1.0"

    def test_items_have_required_fields(self, sample_notes: ReleaseNotes, default_render_config):
        """GIVEN release notes."""
        renderer = JsonRenderer()

        """WHEN rendering."""
        data = json.loads(renderer.render(sample_notes, default_render_config))

        """THEN each item has required fields."""
        for group in data["groups"]:
            for item in group["items"]:
                assert "id" in item
                assert "title" in item
                assert "category" in item
                assert "is_breaking" in item
