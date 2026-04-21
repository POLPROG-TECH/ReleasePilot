"""Tests for date input validation, subtitle length capping, and cross-verification of git, title, and config features."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from releasepilot.domain.models import ReleaseRange

# ── 1. Custom date validation ───────────────────────────────────────────────


class TestDateValidation:
    """Scenarios for _prompt_valid_date rejecting invalid dates and looping until valid."""

    """GIVEN a user entering a valid date string"""

    def test_valid_date_accepted(self):
        """WHEN the test exercises valid date accepted"""
        from releasepilot.cli.guide import _prompt_valid_date

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with patch("releasepilot.cli.guide_steps.text_prompt", return_value=yesterday):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the valid date is returned"""
        assert result == yesterday

    """GIVEN a user entering invalid formats then a valid date"""

    def test_invalid_format_rejected_then_valid(self):
        """WHEN the test exercises invalid format rejected then valid"""
        from releasepilot.cli.guide import _prompt_valid_date

        valid = (date.today() - timedelta(days=7)).isoformat()
        calls = iter(["not-a-date", "abc123", valid])
        with (
            patch("releasepilot.cli.guide_steps.text_prompt", side_effect=calls),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the valid date is returned"""
        assert result == valid

    """GIVEN a user entering a future date then a valid past date"""

    def test_future_date_rejected(self):
        """WHEN the test exercises future date rejected"""
        from releasepilot.cli.guide import _prompt_valid_date

        future = (date.today() + timedelta(days=30)).isoformat()
        valid = (date.today() - timedelta(days=1)).isoformat()
        calls = iter([future, valid])
        with (
            patch("releasepilot.cli.guide_steps.text_prompt", side_effect=calls),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the valid past date is returned"""
        assert result == valid

    """GIVEN a user entering a date with surrounding whitespace"""

    def test_whitespace_trimmed(self):
        """WHEN the test exercises whitespace trimmed"""
        from releasepilot.cli.guide import _prompt_valid_date

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with patch("releasepilot.cli.guide_steps.text_prompt", return_value=f"  {yesterday}  "):
            """WHEN _prompt_valid_date is called."""
            result = _prompt_valid_date()

        """THEN the trimmed date is returned"""
        assert result == yesterday


# ── 2. Subtitle validation ──────────────────────────────────────────────────


class TestSubtitleValidation:
    """Scenarios for _step_custom_title trimming whitespace and capping length."""

    """GIVEN a user entering a subtitle with surrounding whitespace"""

    def test_whitespace_trimmed(self):
        """WHEN the test exercises whitespace trimmed"""
        from releasepilot.cli.guide import _step_custom_title

        with (
            patch("releasepilot.cli.guide_steps.text_prompt", return_value="  Monthly Release  "),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _step_custom_title is called."""
            result = _step_custom_title("MyApp")

        """THEN the trimmed subtitle is returned"""
        assert result == "Monthly Release"

    """GIVEN a user entering an empty subtitle"""

    def test_empty_allowed(self):
        """WHEN the test exercises empty allowed"""
        from releasepilot.cli.guide import _step_custom_title

        with (
            patch("releasepilot.cli.guide_steps.text_prompt", return_value=""),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _step_custom_title is called."""
            result = _step_custom_title("MyApp")

        """THEN an empty string is returned"""
        assert result == ""

    """GIVEN a user entering a subtitle longer than 200 characters"""

    def test_long_subtitle_trimmed(self):
        """WHEN the test exercises long subtitle trimmed"""
        from releasepilot.cli.guide import _step_custom_title

        long_text = "A" * 250
        with (
            patch("releasepilot.cli.guide_steps.text_prompt", return_value=long_text),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _step_custom_title is called."""
            result = _step_custom_title("MyApp")

        """THEN the subtitle is trimmed to 200 characters"""
        assert len(result) == 200


# ── 3. Verify branch validation still works (Phase 15) ──────────────────────


class TestBranchValidationPresent:
    """Scenarios for _prompt_valid_branch rejecting invalid branches."""

    """GIVEN a user entering a valid branch name"""

    def test_valid_branch_accepted(self):
        """WHEN the test exercises valid branch accepted"""
        from releasepilot.cli.guide import _prompt_valid_branch

        with patch("releasepilot.cli.guide_steps.text_prompt", return_value="main"):
            """WHEN _prompt_valid_branch is called."""
            result = _prompt_valid_branch(["main", "develop"])

        """THEN the valid branch is returned"""
        assert result == "main"

    """GIVEN a user entering an invalid branch then a valid one"""

    def test_invalid_then_valid(self):
        """WHEN the test exercises invalid then valid"""
        from releasepilot.cli.guide import _prompt_valid_branch

        calls = iter(["nope", "main"])
        with (
            patch("releasepilot.cli.guide_steps.text_prompt", side_effect=calls),
            patch("releasepilot.cli.guide_steps.console"),
        ):
            """WHEN _prompt_valid_branch is called."""
            result = _prompt_valid_branch(["main", "develop"])

        """THEN the valid branch is returned"""
        assert result == "main"


# ── 4. Verify title structure (Phase 16) ─────────────────────────────────────


class TestTitleStructure:
    """Scenarios for ReleaseRange storing app_name separately from subtitle."""

    """GIVEN a ReleaseRange with app_name and title"""

    def test_display_title_with_app_name(self):
        """WHEN the test exercises display title with app name"""
        rr = ReleaseRange(
            from_ref="v1",
            to_ref="v2",
            app_name="LoopIt",
            title="Release Brief",
        )

        """THEN display_title includes app_name and subtitle excludes it"""
        assert rr.display_title == "LoopIt - Release Brief"
        assert rr.subtitle == "Release Brief"

    """GIVEN a ReleaseRange without app_name"""

    def test_display_title_without_app_name(self):
        """WHEN the test exercises display title without app name"""
        rr = ReleaseRange(from_ref="v1", to_ref="v2", title="Notes")

        """THEN display_title equals title and app_name is empty"""
        assert rr.display_title == "Notes"
        assert rr.app_name == ""


# ── 5. Verify overwrite default (Phase 16) ──────────────────────────────────


class TestOverwriteDefault:
    """Scenarios for overwrite being the default option."""

    """GIVEN the source code of _confirm_overwrite_or_rename"""

    def test_default_index_is_zero(self):
        """WHEN the test exercises default index is zero"""
        import inspect

        from releasepilot.cli.guide import _confirm_overwrite_or_rename

        source = inspect.getsource(_confirm_overwrite_or_rename)

        """THEN default_index=0 is present in the source"""
        assert "default_index=0" in source


# ── 6. Verify git arg ordering (Phase 15) ────────────────────────────────────


class TestGitArgOrdering:
    """Scenarios for git options appearing before positional branch argument."""

    """GIVEN the source code of collect_by_date"""

    def test_collect_by_date_branch_last(self):
        import inspect

        from releasepilot.sources.git import GitSourceCollector

        source = inspect.getsource(GitSourceCollector.collect_by_date)

        """WHEN line positions of --since and branch are compared"""
        # The branch param should be after --since and --pretty lines
        lines = source.split("\n")
        since_line = next(i for i, ln in enumerate(lines) if "--since=" in ln)
        branch_line = next(i for i, ln in enumerate(lines) if "branch," in ln)

        """THEN branch argument appears after --since"""
        assert branch_line > since_line


# ── 7. Verify JSON schema exists ────────────────────────────────────────────


class TestJsonSchemaExists:
    """Scenarios for JSON schema config validation file."""

    """GIVEN the expected schema file path"""

    def test_schema_file_present(self):
        """WHEN the test exercises schema file present"""
        from pathlib import Path

        schema = Path(__file__).parent.parent / "schema" / "releasepilot.schema.json"

        """THEN the file exists"""
        assert schema.is_file()

    """GIVEN the schema file loaded as JSON"""

    def test_schema_valid_json(self):
        """WHEN the test exercises schema valid json"""
        import json
        from pathlib import Path

        schema = Path(__file__).parent.parent / "schema" / "releasepilot.schema.json"
        data = json.loads(schema.read_text())

        """THEN it has the expected type and properties"""
        assert data["type"] == "object"
        assert "branch" in data["properties"]


# ── 8. Verify PipelineStats fields ──────────────────────────────────────────


class TestPipelineStatsFields:
    """Scenarios for PipelineStats having all required fields."""

    """GIVEN a default PipelineStats instance"""

    def test_stats_fields(self):
        """WHEN the test exercises stats fields"""
        from releasepilot.pipeline.orchestrator import PipelineStats

        stats = PipelineStats()

        """THEN all required fields are present"""
        assert hasattr(stats, "raw")
        assert hasattr(stats, "after_filter")
        assert hasattr(stats, "after_dedup")
        assert hasattr(stats, "final")
        assert hasattr(stats, "category_counts")
        assert hasattr(stats, "contributor_count")
        assert hasattr(stats, "scopes")
