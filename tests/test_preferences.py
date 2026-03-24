"""Tests for the smart defaults / preferences system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from releasepilot.cli.preferences import (
    PROMOTION_THRESHOLD,
    get_preferred_default,
    record_choice,
    reset_preferences,
)


@pytest.fixture(autouse=True)
def _isolate_prefs(tmp_path: Path, monkeypatch):
    """Redirect preferences to a temp directory for test isolation."""
    prefs_dir = tmp_path / ".config" / "releasepilot"
    prefs_file = prefs_dir / "preferences.json"
    monkeypatch.setattr("releasepilot.cli.preferences.PREFS_DIR", prefs_dir)
    monkeypatch.setattr("releasepilot.cli.preferences.PREFS_FILE", prefs_file)
    # Ensure prefs are enabled
    monkeypatch.delenv("RELEASEPILOT_NO_PREFS", raising=False)


class TestRecordChoice:
    """Scenarios for recording choices."""

    def test_records_single_choice(self, tmp_path: Path):
        """GIVEN an empty preferences store."""

        """WHEN a single choice is recorded."""
        record_choice("audience", "changelog")

        """THEN the preferences file contains the choice with count 1."""
        prefs_file = tmp_path / ".config" / "releasepilot" / "preferences.json"
        data = json.loads(prefs_file.read_text())
        assert data["audience"]["changelog"] == 1

    def test_increments_existing_choice(self):
        """GIVEN an empty preferences store."""

        """WHEN the same choice is recorded three times."""
        record_choice("audience", "executive")
        record_choice("audience", "executive")
        record_choice("audience", "executive")

        """THEN the count for that choice is 3."""
        # After 3 records, count should be 3
        from releasepilot.cli.preferences import _load

        data = _load()
        assert data["audience"]["executive"] == 3

    def test_multiple_keys_independent(self):
        """GIVEN an empty preferences store."""

        """WHEN choices are recorded under different keys."""
        record_choice("audience", "user")
        record_choice("format", "pdf")

        """THEN each key tracks its count independently."""
        from releasepilot.cli.preferences import _load

        data = _load()
        assert data["audience"]["user"] == 1
        assert data["format"]["pdf"] == 1


class TestGetPreferredDefault:
    """Scenarios for preferred default selection."""

    def test_returns_none_below_threshold(self):
        """GIVEN a choice recorded below the promotion threshold."""
        for _ in range(PROMOTION_THRESHOLD - 1):
            record_choice("audience", "executive")
        choices = [("Standard", "changelog"), ("Executive", "executive")]

        """WHEN the preferred default is requested."""
        result = get_preferred_default("audience", choices)

        """THEN no default is promoted."""
        assert result is None

    def test_returns_index_at_threshold(self):
        """GIVEN a choice recorded exactly at the promotion threshold."""
        for _ in range(PROMOTION_THRESHOLD):
            record_choice("audience", "executive")
        choices = [("Standard", "changelog"), ("Executive", "executive")]

        """WHEN the preferred default is requested."""
        result = get_preferred_default("audience", choices)

        """THEN the index of the promoted choice is returned."""
        assert result == 1

    def test_returns_none_for_unknown_key(self):
        """GIVEN no choices have been recorded."""
        choices = [("Standard", "changelog")]

        """WHEN the preferred default is requested for an unknown key."""
        result = get_preferred_default("nonexistent", choices)

        """THEN None is returned."""
        assert result is None

    def test_returns_none_when_value_removed_from_choices(self):
        """GIVEN a choice recorded at the promotion threshold."""
        for _ in range(PROMOTION_THRESHOLD):
            record_choice("audience", "executive")
        # executive is no longer in choices
        choices = [("Standard", "changelog"), ("User", "user")]

        """WHEN the promoted value is absent from the current choices."""
        result = get_preferred_default("audience", choices)

        """THEN None is returned."""
        assert result is None

    def test_picks_highest_count(self):
        """GIVEN multiple choices recorded above the threshold with different counts."""
        for _ in range(PROMOTION_THRESHOLD):
            record_choice("format", "pdf")
        for _ in range(PROMOTION_THRESHOLD + 2):
            record_choice("format", "docx")
        choices = [("PDF", "pdf"), ("DOCX", "docx"), ("MD", "markdown")]

        """WHEN the preferred default is requested."""
        result = get_preferred_default("format", choices)

        """THEN the choice with the highest count is promoted."""
        assert result == 1  # docx


class TestResetPreferences:
    """Scenarios for resetting preferences."""

    def test_reset_clears_all(self, tmp_path: Path):
        """GIVEN a preferences file with recorded choices."""
        record_choice("audience", "executive")
        prefs_file = tmp_path / ".config" / "releasepilot" / "preferences.json"
        assert prefs_file.exists()

        """WHEN preferences are reset."""
        reset_preferences()

        """THEN the preferences file is removed."""
        assert not prefs_file.exists()

    def test_reset_idempotent(self):
        """GIVEN no preferences file exists."""

        """WHEN reset is called twice."""
        reset_preferences()
        reset_preferences()

        """THEN no error is raised."""


class TestDisabledPrefs:
    """Scenarios for disabled preferences."""

    def test_record_noop_when_disabled(self, monkeypatch, tmp_path: Path):
        """GIVEN preferences are disabled via environment variable."""
        monkeypatch.setenv("RELEASEPILOT_NO_PREFS", "1")

        """WHEN a choice is recorded."""
        record_choice("audience", "executive")

        """THEN no preferences file is created."""
        prefs_file = tmp_path / ".config" / "releasepilot" / "preferences.json"
        assert not prefs_file.exists()

    def test_get_preferred_returns_none_when_disabled(self, monkeypatch):
        """GIVEN choices recorded above threshold while prefs are enabled."""
        # First record some prefs while enabled
        for _ in range(PROMOTION_THRESHOLD):
            record_choice("audience", "executive")

        """WHEN preferences are disabled and the default is requested."""
        # Now disable
        monkeypatch.setenv("RELEASEPILOT_NO_PREFS", "1")
        choices = [("Standard", "changelog"), ("Executive", "executive")]
        result = get_preferred_default("audience", choices)

        """THEN None is returned."""
        assert result is None


class TestCorruptedFile:
    """Scenarios for corrupted preferences file."""

    def test_handles_corrupted_json(self, tmp_path: Path):
        """GIVEN a preferences file containing invalid JSON."""
        prefs_dir = tmp_path / ".config" / "releasepilot"
        prefs_dir.mkdir(parents=True)
        (prefs_dir / "preferences.json").write_text("NOT JSON!!")

        """WHEN the preferred default is requested."""
        # Should not crash
        result = get_preferred_default("audience", [("X", "x")])

        """THEN None is returned and recording still works."""
        assert result is None
        # Recording should still work (overwrites corrupted file)
        record_choice("audience", "x")


class TestRepoUrlDetection:
    """Scenarios for repo URL detection."""

    def test_https_github_url(self):
        """GIVEN the repo URL regex pattern."""
        from releasepilot.cli.guide import _REPO_URL_RE

        """WHEN an HTTPS GitHub URL is tested."""
        result = _REPO_URL_RE.match("https://github.com/user/repo")

        """THEN it matches."""
        assert result

    def test_https_git_url(self):
        """GIVEN the repo URL regex pattern."""
        from releasepilot.cli.guide import _REPO_URL_RE

        """WHEN an HTTPS .git URL is tested."""
        result = _REPO_URL_RE.match("https://github.com/user/repo.git")

        """THEN it matches."""
        assert result

    def test_ssh_git_url(self):
        """GIVEN the repo URL regex pattern."""
        from releasepilot.cli.guide import _REPO_URL_RE

        """WHEN an SSH git URL is tested."""
        result = _REPO_URL_RE.match("git@github.com:user/repo.git")

        """THEN it matches."""
        assert result

    def test_local_path_not_matched(self):
        """GIVEN the repo URL regex pattern."""
        from releasepilot.cli.guide import _REPO_URL_RE

        """WHEN absolute or dot paths are tested."""
        """THEN they do not match."""
        assert not _REPO_URL_RE.match("/path/to/repo")
        assert not _REPO_URL_RE.match(".")

    def test_relative_path_not_matched(self):
        """GIVEN the repo URL regex pattern."""
        from releasepilot.cli.guide import _REPO_URL_RE

        """WHEN a relative path is tested."""
        """THEN it does not match."""
        assert not _REPO_URL_RE.match("../other-repo")


class TestResetPreferencesCli:
    """Scenarios for reset-preferences CLI flag."""

    def test_reset_flag(self, tmp_path: Path, monkeypatch):
        """GIVEN a preferences file with existing data."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        # Isolate prefs
        prefs_dir = tmp_path / ".config" / "releasepilot"
        prefs_file = prefs_dir / "preferences.json"
        monkeypatch.setattr("releasepilot.cli.preferences.PREFS_DIR", prefs_dir)
        monkeypatch.setattr("releasepilot.cli.preferences.PREFS_FILE", prefs_file)

        # Create a dummy pref file
        prefs_dir.mkdir(parents=True)
        prefs_file.write_text('{"audience": {"executive": 5}}')

        """WHEN the CLI is invoked with --reset-preferences."""
        runner = CliRunner()
        result = runner.invoke(cli, ["guide", "--reset-preferences"])

        """THEN preferences are cleared and success is reported."""
        assert result.exit_code == 0
        assert "cleared" in result.output.lower()
        assert not prefs_file.exists()
