"""Phase 15 tests: branch validation, git arg order, subtitle, overwrite."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from releasepilot.sources.git import GitSourceCollector

# ── Git argument ordering ────────────────────────────────────────────────────

class TestGitArgOrder:
    """Scenarios for git CLI argument ordering."""

    def test_collect_by_date_options_before_branch(self, tmp_path: Path) -> None:
        """GIVEN a GitSourceCollector with a mocked _run_git."""
        git = GitSourceCollector(str(tmp_path))
        with patch.object(git, "_run_git", return_value="") as mock:
            """WHEN collect_by_date is called with a date and branch."""
            git.collect_by_date("2025-01-01", "main")
            args = mock.call_args[0][0]

            """THEN --since comes before the positional branch argument."""
            assert args[-1] == "main"
            since_idx = next(i for i, a in enumerate(args) if a.startswith("--since"))
            branch_idx = args.index("main")
            assert since_idx < branch_idx

    def test_collect_by_date_options_before_head(self, tmp_path: Path) -> None:
        """GIVEN a GitSourceCollector with a mocked _run_git."""
        git = GitSourceCollector(str(tmp_path))
        with patch.object(git, "_run_git", return_value="") as mock:
            """WHEN collect_by_date is called without an explicit branch."""
            git.collect_by_date("2025-06-01")
            args = mock.call_args[0][0]

            """THEN HEAD is the last positional argument."""
            assert args[-1] == "HEAD"

    def test_run_git_log_options_before_range(self, tmp_path: Path) -> None:
        """GIVEN a GitSourceCollector with a mocked _run_git."""
        git = GitSourceCollector(str(tmp_path))
        with patch.object(git, "_run_git", return_value="") as mock:
            """WHEN _run_git_log is called with a range."""
            git._run_git_log("v1.0", "HEAD")
            args = mock.call_args[0][0]

            """THEN --pretty comes before the positional range argument."""
            assert args[-1] == "v1.0..HEAD"
            pretty_idx = next(i for i, a in enumerate(args) if a.startswith("--pretty"))
            range_idx = args.index("v1.0..HEAD")
            assert pretty_idx < range_idx

    def test_first_commit_date_branch_after_options(self, tmp_path: Path) -> None:
        """GIVEN a GitSourceCollector with a mocked _run_git returning a date."""
        git = GitSourceCollector(str(tmp_path))
        with patch.object(git, "_run_git", return_value="commit abc\n2025-01-01T00:00:00Z") as mock:
            """WHEN first_commit_date is called with a specific branch."""
            git.first_commit_date(branch="develop")
            args = mock.call_args[0][0]

            """THEN the branch is the last argument, using rev-list."""
            assert args[-1] == "develop"
            assert "rev-list" in args
            assert "--max-parents=0" in args

    def test_first_commit_date_head_when_no_branch(self, tmp_path: Path) -> None:
        """GIVEN a GitSourceCollector with a mocked _run_git returning a date."""
        git = GitSourceCollector(str(tmp_path))
        with patch.object(git, "_run_git", return_value="commit abc\n2025-01-01T00:00:00Z") as mock:
            """WHEN first_commit_date is called without a branch."""
            git.first_commit_date()
            args = mock.call_args[0][0]

            """THEN HEAD is the last argument."""
            assert args[-1] == "HEAD"

    def test_collect_by_date_real_git(self, tmp_path: Path) -> None:
        """GIVEN a real git repository with one commit."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "t@t.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"],
            capture_output=True,
        )
        (repo / "f.txt").write_text("hello")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "feat: init"],
            capture_output=True,
        )

        """WHEN collect_by_date is called against the real repo."""
        git = GitSourceCollector(str(repo))
        items = git.collect_by_date("2020-01-01", "HEAD")

        """THEN at least one commit item is returned without arg-order errors."""
        assert len(items) >= 1


# ── Branch validation ────────────────────────────────────────────────────────

class TestBranchValidation:
    """Scenarios for branch name validation prompts."""

    def test_prompt_valid_branch_accepts_valid(self) -> None:
        """GIVEN a list of valid branches and a prompt returning 'main'."""
        from releasepilot.cli.guide import _prompt_valid_branch

        with patch("releasepilot.cli.guide.text_prompt", return_value="main"):
            """WHEN _prompt_valid_branch is called."""
            result = _prompt_valid_branch(["main", "develop", "feature/x"])

            """THEN the valid branch is accepted and returned."""
            assert result == "main"

    def test_prompt_valid_branch_rejects_then_accepts(self) -> None:
        """GIVEN a prompt that first returns an invalid branch, then a valid one."""
        from releasepilot.cli.guide import _prompt_valid_branch

        with (
            patch("releasepilot.cli.guide.text_prompt", side_effect=["nope", "develop"]),
            patch("releasepilot.cli.guide.console"),
        ):
            """WHEN _prompt_valid_branch is called."""
            result = _prompt_valid_branch(["main", "develop"])

            """THEN the second (valid) branch is returned."""
            assert result == "develop"


# ── Subtitle refactor ────────────────────────────────────────────────────────

class TestCustomTitleStep:
    """Scenarios for the custom title step."""

    def test_function_exists(self) -> None:
        """GIVEN the guide module."""
        from releasepilot.cli.guide import _step_custom_title

        """WHEN checking for _step_custom_title."""

        """THEN it exists and is callable."""
        assert callable(_step_custom_title)

    def test_returns_user_input(self) -> None:
        """GIVEN a text prompt returning 'Monthly Overview'."""
        from releasepilot.cli.guide import _step_custom_title

        with (
            patch("releasepilot.cli.guide.text_prompt", return_value="Monthly Overview"),
            patch("releasepilot.cli.guide.console"),
        ):
            """WHEN _step_custom_title is called."""
            result = _step_custom_title("MyRepo")

            """THEN the user-provided title is returned."""
            assert result == "Monthly Overview"

    def test_returns_empty_for_skip(self) -> None:
        """GIVEN a text prompt returning an empty string."""
        from releasepilot.cli.guide import _step_custom_title

        with (
            patch("releasepilot.cli.guide.text_prompt", return_value=""),
            patch("releasepilot.cli.guide.console"),
        ):
            """WHEN _step_custom_title is called."""
            result = _step_custom_title("MyRepo")

            """THEN an empty string is returned."""
            assert result == ""

    def test_old_step_app_name_removed(self) -> None:
        """GIVEN the guide module."""
        import releasepilot.cli.guide as guide_mod

        """WHEN checking for the old _step_app_name function."""

        """THEN it no longer exists."""
        assert not hasattr(guide_mod, "_step_app_name")


# ── Overwrite confirmation ───────────────────────────────────────────────────

class TestOverwriteConfirmation:
    """Scenarios for overwrite-or-rename confirmation."""

    def test_no_existing_file(self, tmp_path: Path) -> None:
        """GIVEN a target path that does not exist yet."""
        from releasepilot.cli.guide import _confirm_overwrite_or_rename

        target = str(tmp_path / "new_file.md")

        """WHEN _confirm_overwrite_or_rename is called."""
        result = _confirm_overwrite_or_rename(target)

        """THEN the original target path is returned unchanged."""
        assert result == target

    def test_overwrite_choice(self, tmp_path: Path) -> None:
        """GIVEN an existing file and a user choosing 'overwrite'."""
        from releasepilot.cli.guide import _confirm_overwrite_or_rename

        existing = tmp_path / "existing.md"
        existing.write_text("old")

        with (
            patch("releasepilot.cli.guide.select_one", return_value="overwrite"),
            patch("releasepilot.cli.guide.console"),
        ):
            """WHEN _confirm_overwrite_or_rename is called."""
            result = _confirm_overwrite_or_rename(str(existing))

            """THEN the existing path is returned for overwriting."""
            assert result == str(existing)

    def test_cancel_choice(self, tmp_path: Path) -> None:
        """GIVEN an existing file and a user choosing 'cancel'."""
        from releasepilot.cli.guide import _confirm_overwrite_or_rename

        existing = tmp_path / "existing.md"
        existing.write_text("old")

        with (
            patch("releasepilot.cli.guide.select_one", return_value="cancel"),
            patch("releasepilot.cli.guide.console"),
        ):
            """WHEN _confirm_overwrite_or_rename is called."""
            result = _confirm_overwrite_or_rename(str(existing))

            """THEN None is returned to indicate cancellation."""
            assert result is None

    def test_rename_to_new(self, tmp_path: Path) -> None:
        """GIVEN an existing file and a user choosing 'rename' with a new name."""
        from releasepilot.cli.guide import _confirm_overwrite_or_rename

        existing = tmp_path / "existing.md"
        existing.write_text("old")
        new_name = str(tmp_path / "renamed.md")

        with (
            patch("releasepilot.cli.guide.select_one", return_value="rename"),
            patch("releasepilot.cli.guide.text_prompt", return_value=new_name),
            patch("releasepilot.cli.guide.console"),
        ):
            """WHEN _confirm_overwrite_or_rename is called."""
            result = _confirm_overwrite_or_rename(str(existing))

            """THEN the new renamed path is returned."""
            assert result == new_name


# ── Executive format default ─────────────────────────────────────────────────

class TestExecutiveFormatDefault:
    """Scenarios for executive format defaults."""

    def test_executive_format_choices_start_with_pdf(self) -> None:
        """GIVEN the executive format choices constant."""
        from releasepilot.cli.guide import _FORMAT_CHOICES_EXECUTIVE

        """WHEN inspecting the first choice."""

        """THEN it is 'pdf'."""
        assert _FORMAT_CHOICES_EXECUTIVE[0][1] == "pdf"

    def test_step_format_executive_defaults_to_pdf(self) -> None:
        """GIVEN a select_one mock returning 'pdf'."""
        from releasepilot.cli.guide import _step_format_executive

        with patch("releasepilot.cli.guide.select_one", return_value="pdf"):
            """WHEN _step_format_executive is called."""
            result = _step_format_executive(lambda *a: 0)

            """THEN 'pdf' is returned as the selected format."""
            assert result == "pdf"
