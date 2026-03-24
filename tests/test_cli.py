"""Tests for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from releasepilot.cli.app import cli


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture(autouse=False)
def isolated_dir(tmp_path, monkeypatch):
    """Run test from an isolated directory so .releasepilot.json is not picked up."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def sample_input_file(tmp_path: Path) -> Path:
    data = {
        "changes": [
            {"title": "Add user profiles", "category": "feature", "scope": "users"},
            {"title": "Fix session timeout", "category": "bugfix", "scope": "auth"},
            {"title": "Improve error messages", "category": "improvement"},
            {"title": "Drop Python 3.10 support", "category": "feature", "breaking": True},
        ]
    }
    file = tmp_path / "changes.json"
    file.write_text(json.dumps(data))
    return file


class TestGenerateCommand:
    """Scenarios for the generate command."""

    def test_generate_from_file(self, runner, sample_input_file, isolated_dir):
        """GIVEN a structured input file."""

        """WHEN running generate."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(sample_input_file),
                "--version",
                "3.0.0",
            ],
        )

        """THEN it succeeds with markdown output."""
        assert result.exit_code == 0
        assert "Version 3.0.0" in result.output
        assert "New Features" in result.output

    def test_generate_json_format(self, runner, sample_input_file):
        """GIVEN a structured input file."""

        """WHEN generating with JSON format."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(sample_input_file),
                "--format",
                "json",
            ],
        )

        """THEN it produces valid JSON."""
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "groups" in data

    def test_generate_user_audience(self, runner, sample_input_file):
        """GIVEN a structured input file."""

        """WHEN generating for user audience."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(sample_input_file),
                "--audience",
                "user",
            ],
        )

        """THEN output hides internal details."""
        assert result.exit_code == 0
        assert "Refactoring" not in result.output

    def test_generate_summary_audience(self, runner, sample_input_file):
        """GIVEN a structured input file."""

        """WHEN generating a summary."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(sample_input_file),
                "--audience",
                "summary",
            ],
        )

        """THEN output is produced."""
        assert result.exit_code == 0


class TestPreviewCommand:
    """Scenarios for the preview command."""

    def test_preview_from_file(self, runner, sample_input_file):
        """GIVEN a structured input file."""

        """WHEN previewing."""
        result = runner.invoke(
            cli,
            [
                "preview",
                "--source-file",
                str(sample_input_file),
                "--version",
                "3.0.0",
            ],
        )

        """THEN it succeeds (rich panel goes to stderr, so just check exit code)."""
        assert result.exit_code == 0


class TestCollectCommand:
    """Scenarios for the collect command."""

    def test_collect_from_file(self, runner, sample_input_file):
        """GIVEN a structured input file."""

        """WHEN collecting."""
        result = runner.invoke(
            cli,
            [
                "collect",
                "--source-file",
                str(sample_input_file),
            ],
        )

        """THEN it shows the collected items."""
        assert result.exit_code == 0


class TestAnalyzeCommand:
    """Scenarios for the analyze command."""

    def test_analyze_from_file(self, runner, sample_input_file):
        """GIVEN a structured input file."""

        """WHEN analyzing."""
        result = runner.invoke(
            cli,
            [
                "analyze",
                "--source-file",
                str(sample_input_file),
            ],
        )

        """THEN it shows analysis output."""
        assert result.exit_code == 0


class TestExportCommand:
    """Scenarios for the export command."""

    def test_export_to_file(self, runner, sample_input_file, tmp_path, isolated_dir):
        """GIVEN a structured input file and an output path."""
        output_file = tmp_path / "RELEASE_NOTES.md"

        """WHEN exporting."""
        result = runner.invoke(
            cli,
            [
                "export",
                "--source-file",
                str(sample_input_file),
                "--version",
                "3.0.0",
                "-o",
                str(output_file),
            ],
        )

        """THEN the file is written."""
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "Version 3.0.0" in content

    def test_export_json(self, runner, sample_input_file, tmp_path):
        """GIVEN output path for JSON."""
        output_file = tmp_path / "release.json"

        """WHEN exporting as JSON."""
        result = runner.invoke(
            cli,
            [
                "export",
                "--source-file",
                str(sample_input_file),
                "--format",
                "json",
                "-o",
                str(output_file),
            ],
        )

        """THEN valid JSON is written."""
        assert result.exit_code == 0
        data = json.loads(output_file.read_text())
        assert "groups" in data


class TestErrorHandling:
    """Scenarios for CLI error handling."""

    def test_missing_source_file(self, runner):
        """GIVEN a nonexistent source file."""

        """WHEN generating."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                "/nonexistent/file.json",
            ],
        )

        """THEN it fails gracefully."""
        assert result.exit_code != 0

    def test_version_flag(self, runner):
        """GIVEN the CLI."""

        """WHEN requesting version."""
        result = runner.invoke(cli, ["--version"])

        """THEN version is shown."""
        assert "1.0.0" in result.output


class TestIsolatedGenerate:
    """Regression: generate command works from an isolated directory (no config pollution)."""

    def test_generate_isolated_no_config(self, runner, sample_input_file, isolated_dir):
        """GIVEN an isolated tmp directory with no .releasepilot.json."""

        """WHEN generating release notes."""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                str(sample_input_file),
                "--version",
                "4.0.0",
            ],
        )

        """THEN output uses plain 'Version X.Y.Z' heading (no app_name leak)."""
        assert result.exit_code == 0
        assert "Version 4.0.0" in result.output
        assert "TEST" not in result.output
