"""Tests for CLI error handling, validation, and user-friendly messages."""

from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from releasepilot.cli.app import cli
from releasepilot.cli.errors import (
    UserError,
    git_command_failed,
    no_tags_found,
    not_a_git_repo,
    ref_not_found,
    source_file_not_found,
)
from releasepilot.cli.validators import (
    validate_export_path,
    validate_settings,
)
from releasepilot.config.settings import Settings


class TestUserError:
    """Scenarios for UserError construction."""

    """GIVEN a UserError with a summary"""

    def test_error_has_summary(self):
        err = UserError(summary="Test error")

        """WHEN accessing the summary"""

        """THEN it matches the provided value"""
        assert err.summary == "Test error"

    """GIVEN a UserError with full context"""

    def test_error_with_full_context(self):
        err = UserError(
            summary="Test",
            reason="Because X",
            suggestions=["Try Y"],
            commands=["cmd Z"],
            hint="Hint A",
        )

        """WHEN accessing error fields"""

        """THEN all context is preserved"""
        assert err.reason == "Because X"
        assert "Try Y" in err.suggestions
        assert "cmd Z" in err.commands
        assert err.hint == "Hint A"

    """GIVEN a fully-populated error"""

    def test_display_does_not_raise(self, capsys):
        err = UserError(
            summary="Test display",
            reason="Reason",
            suggestions=["Fix it"],
            commands=["releasepilot guide"],
            hint="A helpful hint",
        )

        """WHEN displaying"""
        err.display()

        """THEN it does not raise (output goes to stderr via rich)"""


class TestErrorFactories:
    """Scenarios for error factory functions."""

    """GIVEN a path that is not a git repository"""

    def test_not_a_git_repo(self):
        """WHEN creating the error"""
        err = not_a_git_repo("/tmp/foo")

        """THEN the error describes the issue"""
        assert "git repository" in err.summary.lower()
        assert "/tmp/foo" in err.reason
        assert len(err.suggestions) > 0

    """GIVEN a nonexistent tag reference"""

    def test_ref_not_found(self):
        """WHEN creating the error"""
        err = ref_not_found("v99.0.0", "tag")

        """THEN the error includes the ref and kind"""
        assert "v99.0.0" in err.summary
        assert "tag" in err.summary

    """GIVEN a repository path with no tags"""

    def test_no_tags_found(self):
        """WHEN creating the error"""
        err = no_tags_found(".")

        """THEN the error mentions tags and suggests commands"""
        assert "tags" in err.summary.lower()
        assert len(err.commands) > 0

    """GIVEN a missing source file path"""

    def test_source_file_not_found(self):
        """WHEN creating the error"""
        err = source_file_not_found("missing.json")

        """THEN the error includes the file name"""
        assert "missing.json" in err.summary

    """GIVEN a git error mentioning unknown revision"""

    def test_git_command_failed_unknown_revision(self):
        """WHEN creating the error"""
        err = git_command_failed("fatal: ambiguous argument 'v1.0.0..v1.1.0': unknown revision")

        """THEN the error identifies the missing ref"""
        assert "not found" in err.summary.lower()
        assert "v1.0.0..v1.1.0" in err.summary

    """GIVEN a git error about not being a repository"""

    def test_git_command_failed_not_a_repo(self):
        """WHEN creating the error"""
        err = git_command_failed("fatal: not a git repository")

        """THEN the error mentions git repository"""
        assert "git repository" in err.summary.lower()

    """GIVEN an unrecognized git error"""

    def test_git_command_failed_generic(self):
        """WHEN creating the error"""
        err = git_command_failed("some unknown error")

        """THEN a generic failure message is returned"""
        assert "failed" in err.summary.lower()


class TestValidateSettings:
    """Scenarios for settings validation."""

    """GIVEN a valid JSON source file"""

    def test_valid_source_file(self, tmp_path: Path):
        f = tmp_path / "changes.json"
        f.write_text('{"changes":[]}')
        settings = Settings(source_file=str(f))

        """WHEN validating settings"""
        result = validate_settings(settings)

        """THEN no error is returned"""
        assert result is None

    """GIVEN a nonexistent source file path"""

    def test_missing_source_file(self):
        settings = Settings(source_file="/nonexistent/file.json")

        """WHEN validating settings"""
        result = validate_settings(settings)

        """THEN a not-found error is returned"""
        assert result is not None
        assert "not found" in result.summary.lower()

    """GIVEN a path that is not a git repository"""

    def test_not_a_git_repo(self, tmp_path: Path):
        settings = Settings(repo_path=str(tmp_path))

        """WHEN validating settings"""
        result = validate_settings(settings)

        """THEN a git repository error is returned"""
        assert result is not None
        assert "git repository" in result.summary.lower()

    """GIVEN a valid git repository with settings"""

    def test_valid_git_repo(self, tmp_path: Path):
        _init_repo(tmp_path)
        settings = Settings(
            repo_path=str(tmp_path),
            since_date="2025-01-01",
            branch="main",
        )

        """WHEN validating settings"""
        result = validate_settings(settings)

        """THEN no error is returned"""
        assert result is None

    """GIVEN a git repo with an invalid since_date"""

    def test_invalid_date(self, tmp_path: Path):
        _init_repo(tmp_path)
        settings = Settings(
            repo_path=str(tmp_path),
            since_date="not-a-date",
        )

        """WHEN validating settings"""
        result = validate_settings(settings)

        """THEN a date-related error is returned"""
        assert result is not None
        assert "date" in result.summary.lower()

    """GIVEN a git repo with a nonexistent from_ref"""

    def test_invalid_ref(self, tmp_path: Path):
        _init_repo(tmp_path)
        settings = Settings(
            repo_path=str(tmp_path),
            from_ref="v99.99.99",
        )

        """WHEN validating settings"""
        result = validate_settings(settings)

        """THEN a not-found error is returned"""
        assert result is not None
        assert "not found" in result.summary.lower()


class TestValidateExportPath:
    """Scenarios for export path validation."""

    """GIVEN a valid export directory"""

    def test_valid_path(self, tmp_path: Path):
        """WHEN validating the export path"""
        result = validate_export_path(str(tmp_path / "output.md"))

        """THEN no error is returned"""
        assert result is None

    """GIVEN a path with a nonexistent parent directory"""

    def test_missing_parent_dir(self):
        """WHEN validating the export path"""
        result = validate_export_path("/nonexistent/dir/output.md")

        """THEN an error about the missing directory is returned"""
        assert result is not None
        assert "does not exist" in result.reason

    """GIVEN an existing file and overwrite disabled"""

    def test_existing_file_without_overwrite(self, tmp_path: Path):
        f = tmp_path / "existing.md"
        f.write_text("old")

        """WHEN validating the export path"""
        result = validate_export_path(str(f), allow_overwrite=False)

        """THEN an already-exists error is returned"""
        assert result is not None
        assert "already exists" in result.summary.lower()

    """GIVEN an existing file and overwrite enabled"""

    def test_existing_file_with_overwrite(self, tmp_path: Path):
        f = tmp_path / "existing.md"
        f.write_text("old")

        """WHEN validating the export path"""
        result = validate_export_path(str(f), allow_overwrite=True)

        """THEN no error is returned"""
        assert result is None


class TestCLIErrorMessages:
    """Scenarios for CLI error messages."""

    """GIVEN a nonexistent repository path"""

    def test_generate_invalid_repo(self):
        runner = CliRunner()

        """WHEN running generate"""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--repo",
                "/nonexistent/repo",
                "--version",
                "1.0.0",
            ],
        )

        """THEN it fails"""
        assert result.exit_code != 0

    """GIVEN a git repo with a nonexistent ref"""

    def test_generate_invalid_ref(self, tmp_path: Path):
        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN running generate with the invalid ref"""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--repo",
                str(tmp_path),
                "--from",
                "v99.99.99",
                "--to",
                "HEAD",
            ],
        )

        """THEN it fails"""
        assert result.exit_code != 0

    """GIVEN a git repo and an invalid date"""

    def test_generate_invalid_date(self, tmp_path: Path):
        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN running generate with the bad date"""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--repo",
                str(tmp_path),
                "--since",
                "bad-date",
            ],
        )

        """THEN it fails"""
        assert result.exit_code != 0

    """GIVEN a nonexistent output directory"""

    def test_export_missing_dir(self, tmp_path: Path):
        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN running export to that directory"""
        result = runner.invoke(
            cli,
            [
                "export",
                "--source-file",
                "examples/sample_changes.json",
                "-o",
                "/nonexistent/dir/out.md",
            ],
        )

        """THEN it fails"""
        assert result.exit_code != 0


class TestDryRun:
    """Scenarios for dry-run mode."""

    """GIVEN a valid source file and the dry-run flag"""

    def test_dry_run_flag(self):
        runner = CliRunner()

        """WHEN running generate with --dry-run"""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                "examples/sample_changes.json",
                "--dry-run",
            ],
        )

        """THEN it succeeds without crashing"""
        assert result.exit_code == 0
        # Dry run output goes to stderr, but should not crash

    """GIVEN a valid source file, version, and the dry-run flag"""

    def test_dry_run_with_version(self):
        runner = CliRunner()

        """WHEN running generate with --dry-run and --version"""
        result = runner.invoke(
            cli,
            [
                "generate",
                "--source-file",
                "examples/sample_changes.json",
                "--version",
                "3.0.0",
                "--dry-run",
            ],
        )

        """THEN it succeeds without crashing"""
        assert result.exit_code == 0


def _init_repo(path: Path) -> None:
    """Create a minimal git repo with one commit."""
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "feat: initial commit"],
        check=True,
        capture_output=True,
    )
