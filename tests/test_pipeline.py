"""Tests for the pipeline orchestrator and structured file source."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from releasepilot.config.settings import Settings
from releasepilot.domain.enums import Audience, OutputFormat
from releasepilot.domain.models import ReleaseRange
from releasepilot.pipeline.orchestrator import collect, compose, process, render
from releasepilot.sources.structured import StructuredFileCollector, StructuredFileError


class TestStructuredFileCollector:
    """Scenarios for StructuredFileCollector."""

    def test_loads_valid_json(self, tmp_path: Path):
        """GIVEN a valid JSON file with changes."""
        data = {
            "changes": [
                {"title": "Add search feature", "category": "feature", "scope": "search"},
                {"title": "Fix typo in docs", "category": "documentation"},
            ]
        }
        file = tmp_path / "changes.json"
        file.write_text(json.dumps(data))

        """WHEN collecting."""
        collector = StructuredFileCollector(str(file))
        items = collector.collect(ReleaseRange(from_ref="", to_ref=""))

        """THEN items are parsed correctly."""
        assert len(items) == 2
        assert items[0].title == "Add search feature"
        assert items[0].scope == "search"

    def test_loads_bare_array(self, tmp_path: Path):
        """GIVEN a JSON file with a bare array."""
        data = [
            {"title": "Item one"},
            {"title": "Item two"},
        ]
        file = tmp_path / "changes.json"
        file.write_text(json.dumps(data))

        """WHEN collecting."""
        collector = StructuredFileCollector(str(file))
        items = collector.collect(ReleaseRange(from_ref="", to_ref=""))

        """THEN items are parsed."""
        assert len(items) == 2

    def test_missing_title_raises(self, tmp_path: Path):
        """GIVEN a JSON file with an entry missing title."""
        data = {"changes": [{"category": "feature"}]}
        file = tmp_path / "changes.json"
        file.write_text(json.dumps(data))

        """WHEN collecting."""
        collector = StructuredFileCollector(str(file))

        """THEN an error is raised."""
        with pytest.raises(StructuredFileError, match="(missing|empty).*title"):
            collector.collect(ReleaseRange(from_ref="", to_ref=""))

    def test_file_not_found_raises(self):
        """GIVEN a nonexistent file."""
        collector = StructuredFileCollector("/nonexistent/file.json")

        """WHEN collecting THEN an error is raised."""
        with pytest.raises(StructuredFileError, match="File not found"):
            collector.collect(ReleaseRange(from_ref="", to_ref=""))

    def test_invalid_json_raises(self, tmp_path: Path):
        """GIVEN an invalid JSON file."""
        file = tmp_path / "bad.json"
        file.write_text("not json {{{")

        """WHEN collecting."""
        collector = StructuredFileCollector(str(file))

        """THEN an error is raised."""
        with pytest.raises(StructuredFileError, match="Invalid JSON"):
            collector.collect(ReleaseRange(from_ref="", to_ref=""))

    def test_breaking_flag_overrides_category(self, tmp_path: Path):
        """GIVEN an item with breaking=true."""
        data = {"changes": [{"title": "Remove API", "category": "feature", "breaking": True}]}
        file = tmp_path / "changes.json"
        file.write_text(json.dumps(data))

        """WHEN collecting."""
        collector = StructuredFileCollector(str(file))
        items = collector.collect(ReleaseRange(from_ref="", to_ref=""))

        """THEN the category is BREAKING."""
        from releasepilot.domain.enums import ChangeCategory

        assert items[0].category == ChangeCategory.BREAKING
        assert items[0].is_breaking is True


class TestPipelineEndToEnd:
    """Scenarios for pipeline end-to-end execution."""

    def test_full_pipeline_from_structured_file(self, tmp_path: Path):
        """GIVEN a structured input file."""
        data = {
            "changes": [
                {"title": "Add OAuth2 support", "category": "feature", "scope": "auth"},
                {"title": "Fix rate limiter bug", "category": "bugfix", "scope": "api"},
                {"title": "Update README", "category": "documentation"},
                {"title": "Remove deprecated v1 routes", "category": "feature", "breaking": True},
                {"title": "Optimize database queries", "category": "performance", "scope": "db"},
            ]
        }
        file = tmp_path / "changes.json"
        file.write_text(json.dumps(data))

        settings = Settings(
            source_file=str(file),
            version="2.0.0",
            audience=Audience.CHANGELOG,
            output_format=OutputFormat.MARKDOWN,
        )

        """WHEN running the pipeline stages."""
        release_range = ReleaseRange(
            from_ref="",
            to_ref="",
            version="2.0.0",
        )
        items = collect(settings, release_range)
        items = process(settings, items)
        notes = compose(settings, items, release_range)
        output = render(settings, notes)

        """THEN the output is valid markdown with expected sections."""
        assert "# Release 2.0.0" in output
        assert "Breaking Changes" in output
        assert "New Features" in output
        assert "Bug Fixes" in output
        assert "Performance" in output

    def test_json_export(self, tmp_path: Path):
        """GIVEN a structured input file."""
        data = {
            "changes": [
                {"title": "New feature", "category": "feature"},
                {"title": "Bug fix", "category": "bugfix"},
            ]
        }
        file = tmp_path / "changes.json"
        file.write_text(json.dumps(data))

        settings = Settings(
            source_file=str(file),
            output_format=OutputFormat.JSON,
        )

        """WHEN running the pipeline."""
        release_range = ReleaseRange(from_ref="", to_ref="")
        items = collect(settings, release_range)
        items = process(settings, items)
        notes = compose(settings, items, release_range)
        output = render(settings, notes)

        """THEN the output is valid JSON."""
        parsed = json.loads(output)
        assert parsed["total_changes"] == 2
        assert len(parsed["groups"]) == 2

    def test_user_audience_hides_internal(self, tmp_path: Path):
        """GIVEN a file with internal and user-facing changes."""
        data = {
            "changes": [
                {"title": "Add dark mode", "category": "feature"},
                {"title": "Refactor DB layer", "category": "refactor"},
                {"title": "Update CI config", "category": "infrastructure"},
            ]
        }
        file = tmp_path / "changes.json"
        file.write_text(json.dumps(data))

        settings = Settings(
            source_file=str(file),
            audience=Audience.USER,
            output_format=OutputFormat.MARKDOWN,
        )

        """WHEN running the pipeline."""
        release_range = ReleaseRange(from_ref="", to_ref="")
        items = collect(settings, release_range)
        items = process(settings, items)
        notes = compose(settings, items, release_range)
        output = render(settings, notes)

        """THEN internal categories are not in output."""
        assert "Refactoring" not in output
        assert "Infrastructure" not in output
        assert "New Features" in output
