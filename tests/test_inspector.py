"""Tests for repository inspector."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from releasepilot.sources.inspector import (
    RepoInspection,
    inspect_repo,
)


class TestInspectRepo:
    """Scenarios for repository inspection."""

    def test_nonexistent_path(self, tmp_path: Path):
        """GIVEN a path that does not exist."""
        bad_path = str(tmp_path / "nonexistent")

        """WHEN inspecting the path."""
        result = inspect_repo(bad_path)

        """THEN it is not a valid repo."""
        assert result.is_valid_repo is False
        assert "does not exist" in result.error

    def test_not_a_git_repo(self, tmp_path: Path):
        """GIVEN a regular directory that is not a git repo."""

        """WHEN inspecting the directory."""
        result = inspect_repo(str(tmp_path))

        """THEN it is not a valid repo."""
        assert result.is_valid_repo is False
        assert "Not a git repository" in result.error

    def test_valid_git_repo(self, tmp_path: Path):
        """GIVEN a freshly initialized git repo with a commit."""
        _init_repo(tmp_path)

        """WHEN inspecting the repo."""
        result = inspect_repo(str(tmp_path))

        """THEN it is valid with correct metadata."""
        assert result.is_valid_repo is True
        assert result.has_commits is True
        assert len(result.branches) >= 1

    def test_detects_main_as_default(self, tmp_path: Path):
        """GIVEN a repo with 'main' branch."""
        _init_repo(tmp_path, branch="main")

        """WHEN inspecting the repo."""
        result = inspect_repo(str(tmp_path))

        """THEN default branch is 'main'."""
        assert result.default_branch == "main"

    def test_detects_master_as_default(self, tmp_path: Path):
        """GIVEN a repo with 'master' branch."""
        _init_repo(tmp_path, branch="master")

        """WHEN inspecting the repo."""
        result = inspect_repo(str(tmp_path))

        """THEN default branch is 'master'."""
        assert result.default_branch == "master"

    def test_finds_changelog_file(self, tmp_path: Path):
        """GIVEN a repo with a CHANGELOG.md."""
        _init_repo(tmp_path)
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n")

        """WHEN inspecting the repo."""
        result = inspect_repo(str(tmp_path))

        """THEN the changelog is detected."""
        assert "CHANGELOG.md" in result.changelog_files

    def test_no_changelog(self, tmp_path: Path):
        """GIVEN a repo without changelog files."""
        _init_repo(tmp_path)

        """WHEN inspecting the repo."""
        result = inspect_repo(str(tmp_path))

        """THEN no changelogs are found."""
        assert len(result.changelog_files) == 0

    def test_detects_tags(self, tmp_path: Path):
        """GIVEN a repo with tags."""
        _init_repo(tmp_path)
        subprocess.run(
            ["git", "-C", str(tmp_path), "tag", "v1.0.0"],
            check=True,
            capture_output=True,
        )

        """WHEN inspecting the repo."""
        result = inspect_repo(str(tmp_path))

        """THEN tags are listed."""
        assert "v1.0.0" in result.recent_tags


class TestRepoInspection:
    """Scenarios for the RepoInspection data model."""

    def test_inspection_is_frozen(self):
        """GIVEN a RepoInspection instance."""
        inspection = RepoInspection(path="/tmp", is_valid_repo=True)

        """WHEN trying to modify it."""

        """THEN it raises a FrozenInstanceError."""
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            inspection.is_valid_repo = False  # type: ignore[misc]


def _init_repo(path: Path, branch: str = "main") -> None:
    """Helper: create a minimal git repo with one commit."""
    subprocess.run(["git", "init", "-b", branch, str(path)], check=True, capture_output=True)
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
