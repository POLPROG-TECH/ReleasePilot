"""Tests for the guided workflow and date-range support."""

from __future__ import annotations

import subprocess
from datetime import date, timedelta
from pathlib import Path

from click.testing import CliRunner

from releasepilot.cli.app import cli
from releasepilot.config.settings import Settings
from releasepilot.pipeline.orchestrator import build_release_range, collect


class TestDateRangeSettings:
    """Scenarios for date-range settings detection."""

    def test_is_date_range_true(self):
        """GIVEN settings with a since_date."""
        settings = Settings(since_date="2025-01-01")

        """WHEN checking is_date_range."""

        """THEN it returns True."""
        assert settings.is_date_range is True

    def test_is_date_range_false(self):
        """GIVEN settings without a since_date."""
        settings = Settings()

        """WHEN checking is_date_range."""

        """THEN it returns False."""
        assert settings.is_date_range is False


class TestDateRangePipeline:
    """Scenarios for date-range pipeline building."""

    def test_build_release_range_with_date(self):
        """GIVEN settings with a date range."""
        settings = Settings(since_date="2025-01-01", branch="main", version="1.0.0")

        """WHEN building the release range."""
        rr = build_release_range(settings)

        """THEN the range uses the date and branch."""
        assert rr.from_ref == "2025-01-01"
        assert rr.to_ref == "main"
        assert rr.version == "1.0.0"
        assert "since 2025-01-01" in rr.display_title
        assert "Release 1.0.0" in rr.display_title

    def test_date_range_collection_from_real_repo(self, tmp_path: Path):
        """GIVEN a git repo with commits and date-range settings."""
        _init_repo_with_commits(tmp_path)

        settings = Settings(
            repo_path=str(tmp_path),
            since_date=(date.today() - timedelta(days=7)).isoformat(),
            branch="main",
        )

        """WHEN collecting changes by date."""
        rr = build_release_range(settings)
        items = collect(settings, rr)

        """THEN recent commits are found."""
        assert len(items) >= 1


class TestDateRangeCLI:
    """Scenarios for date-range CLI generation."""

    def test_generate_with_since_flag(self, tmp_path: Path):
        """GIVEN a git repo and the CLI."""
        _init_repo_with_commits(tmp_path)
        runner = CliRunner()
        since = (date.today() - timedelta(days=30)).isoformat()

        """WHEN running generate with --since."""
        result = runner.invoke(cli, [
            "generate",
            "--repo", str(tmp_path),
            "--since", since,
            "--branch", "main",
        ])

        """THEN it succeeds."""
        assert result.exit_code == 0

    def test_generate_with_since_and_version(self, tmp_path: Path):
        """GIVEN a git repo and the CLI."""
        _init_repo_with_commits(tmp_path)
        runner = CliRunner()
        since = (date.today() - timedelta(days=30)).isoformat()

        """WHEN running generate with --since and --version."""
        result = runner.invoke(cli, [
            "generate",
            "--repo", str(tmp_path),
            "--since", since,
            "--version", "2.0.0",
        ])

        """THEN it includes the version in output."""
        assert result.exit_code == 0
        assert "2.0.0" in result.output
        assert "Release 2.0.0" in result.output


class TestGuideCLI:
    """Scenarios for the guided CLI workflow."""

    def test_guide_with_invalid_repo(self):
        """GIVEN a nonexistent repo path."""
        runner = CliRunner()

        """WHEN running guide."""
        result = runner.invoke(cli, ["guide", "/nonexistent/repo"])

        """THEN it fails gracefully with an error message."""
        assert result.exit_code != 0

    def test_guide_command_exists(self):
        """GIVEN the CLI."""
        runner = CliRunner()

        """WHEN requesting help for guide."""
        result = runner.invoke(cli, ["guide", "--help"])

        """THEN it shows help text."""
        assert result.exit_code == 0
        assert "Interactive guided workflow" in result.output


def _init_repo_with_commits(path: Path) -> None:
    """Create a git repo with several realistic commits."""
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True, capture_output=True,
    )

    commits = [
        ("feat: add user authentication", "auth.py"),
        ("fix(api): resolve timeout issue", "api.py"),
        ("docs: update README", "README.md"),
        ("perf: optimize database queries", "db.py"),
        ("feat(ui): add dark mode support", "ui.py"),
    ]

    for message, filename in commits:
        (path / filename).write_text(f"# {filename}\n")
        subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(path), "commit", "-m", message],
            check=True, capture_output=True,
        )


class TestDateRangeClamping:
    """Scenarios for date-range clamping to repository history."""

    def test_first_commit_date_detection(self, tmp_path: Path):
        """GIVEN a git repo with commits."""
        _init_repo_with_commits(tmp_path)
        from releasepilot.sources.git import GitSourceCollector

        git = GitSourceCollector(str(tmp_path))

        """WHEN detecting the first commit date."""
        first = git.first_commit_date()

        """THEN the oldest commit date is returned."""
        assert first is not None
        # The date portion should be today (commits were just created)
        assert date.today().isoformat() in first

    def test_clamp_warns_when_range_exceeds_history(self, tmp_path: Path):
        """GIVEN a git repo and a date far before its history."""
        _init_repo_with_commits(tmp_path)
        from releasepilot.cli.guide import _clamp_to_repo_history

        """WHEN clamping a date before the first commit."""
        result = _clamp_to_repo_history("2000-01-01", str(tmp_path))

        """THEN the date is clamped to the first commit date."""
        assert result != "2000-01-01"
        assert date.today().isoformat() == result

    def test_clamp_preserves_valid_range(self, tmp_path: Path):
        """GIVEN a git repo and a date within its history."""
        _init_repo_with_commits(tmp_path)
        from releasepilot.cli.guide import _clamp_to_repo_history

        today = date.today().isoformat()

        """WHEN clamping a valid date."""
        result = _clamp_to_repo_history(today, str(tmp_path))

        """THEN the date is preserved unchanged."""
        assert result == today
