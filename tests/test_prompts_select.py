"""Tests for interactive prompt validation and keyboard navigation.

Validates that:
- Out-of-range numeric choices are rejected with clear messages
- Non-numeric input is rejected with clear messages
- Invalid input triggers re-prompt with choices re-displayed
- Valid input returns the correct value
- Empty input selects the default
- All guided workflow steps validate consistently
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
from click.testing import CliRunner

from releasepilot.cli.prompts import confirm, select_one, text_prompt

# ── Helpers ──────────────────────────────────────────────────────────────────

_SAMPLE_CHOICES = [
    ("Option A", "a"),
    ("Option B", "b"),
    ("Option C", "c"),
]


def _run_select(input_text: str, choices=None, default_index: int = 0, hint=None):
    """Run select_one inside a click command so CliRunner can feed input."""
    choices = choices or _SAMPLE_CHOICES

    @click.command()
    def cmd():
        result = select_one(
            "Test menu",
            choices,
            default_index=default_index,
            hint=hint,
        )
        click.echo(f"RESULT:{result}")

    runner = CliRunner()
    return runner.invoke(cmd, input=input_text)


def _run_confirm(input_text: str, default: bool = False):
    """Run confirm inside a click command."""

    @click.command()
    def cmd():
        result = confirm("Continue?", default=default)
        click.echo(f"RESULT:{result}")

    runner = CliRunner()
    return runner.invoke(cmd, input=input_text)


def _run_text_prompt(input_text: str, default: str = ""):
    """Run text_prompt inside a click command."""

    @click.command()
    def cmd():
        result = text_prompt("Enter value", default=default)
        click.echo(f"RESULT:{result}")

    runner = CliRunner()
    return runner.invoke(cmd, input=input_text)


def _init_repo(path: Path) -> None:
    """Create a git repo with realistic commits for guide tests."""
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@t.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "T"],
        check=True,
        capture_output=True,
    )
    for msg, fname in [
        ("feat: add login", "login.py"),
        ("fix: resolve crash", "crash.py"),
        ("perf: speed up queries", "db.py"),
    ]:
        (path / fname).write_text(f"# {fname}\n")
        subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(path), "commit", "-m", msg],
            check=True,
            capture_output=True,
        )


class TestSelectOneValid:
    """Scenarios for valid select_one input."""

    """GIVEN a three-choice menu"""

    def test_first_option(self):
        result = _run_select("1\n")

        """WHEN selecting option 1"""

        """THEN the first value is returned"""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    """GIVEN a three-choice menu"""

    def test_second_option(self):
        result = _run_select("2\n")

        """WHEN selecting option 2"""

        """THEN the second value is returned"""
        assert result.exit_code == 0
        assert "RESULT:b" in result.output

    """GIVEN a three-choice menu"""

    def test_third_option(self):
        result = _run_select("3\n")

        """WHEN selecting option 3"""

        """THEN the third value is returned"""
        assert result.exit_code == 0
        assert "RESULT:c" in result.output

    """GIVEN a three-choice menu with default index 0"""

    def test_default_on_enter(self):
        # Empty input → default (index 0 → "a")

        """WHEN pressing Enter without input"""
        result = _run_select("\n")

        """THEN the default value is returned"""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    """GIVEN a menu with default_index=2"""

    def test_custom_default_index(self):
        # Default index 2 → "c"

        """WHEN pressing Enter"""
        result = _run_select("\n", default_index=2)

        """THEN the third option is returned"""
        assert result.exit_code == 0
        assert "RESULT:c" in result.output

    """GIVEN a single-choice menu"""

    def test_single_choice_menu(self):
        """WHEN selecting option 1"""
        result = _run_select("1\n", choices=[("Only option", "only")])

        """THEN the only value is returned"""
        assert result.exit_code == 0
        assert "RESULT:only" in result.output

    """GIVEN a single-choice menu"""

    def test_single_choice_default(self):
        """WHEN pressing Enter"""
        result = _run_select("\n", choices=[("Only option", "only")])

        """THEN the only value is returned"""
        assert result.exit_code == 0
        assert "RESULT:only" in result.output


class TestSelectOneInvalid:
    """Scenarios for invalid select_one input."""

    """GIVEN a three-choice menu"""

    def test_out_of_range_high(self):
        # 4 is out of range for 3 choices → error, then valid "2"

        """WHEN entering 4 then a valid option"""
        result = _run_select("4\n2\n")

        """THEN the valid follow-up selection is returned"""
        assert result.exit_code == 0
        assert "RESULT:b" in result.output

    """GIVEN a three-choice menu"""

    def test_out_of_range_very_high(self):
        """WHEN entering 99 then a valid option"""
        result = _run_select("99\n1\n")

        """THEN the valid follow-up selection is returned"""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    """GIVEN a three-choice menu"""

    def test_zero_rejected(self):
        """WHEN entering 0 then a valid option"""
        result = _run_select("0\n3\n")

        """THEN the valid follow-up selection is returned"""
        assert result.exit_code == 0
        assert "RESULT:c" in result.output

    """GIVEN a three-choice menu"""

    def test_negative_rejected(self):
        """WHEN entering -1 then a valid option"""
        result = _run_select("-1\n1\n")

        """THEN the valid follow-up selection is returned"""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    """GIVEN a three-choice menu"""

    def test_non_numeric_rejected(self):
        """WHEN entering non-numeric text then a valid option"""
        result = _run_select("abc\n2\n")

        """THEN the valid follow-up selection is returned"""
        assert result.exit_code == 0
        assert "RESULT:b" in result.output

    """GIVEN a three-choice menu"""

    def test_float_rejected(self):
        """WHEN entering a float then a valid option"""
        result = _run_select("1.5\n1\n")

        """THEN the valid follow-up selection is returned"""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    """GIVEN a three-choice menu"""

    def test_special_chars_rejected(self):
        """WHEN entering special characters then a valid option"""
        result = _run_select("@#$\n3\n")

        """THEN the valid follow-up selection is returned"""
        assert result.exit_code == 0
        assert "RESULT:c" in result.output

    """GIVEN a three-choice menu"""

    def test_multiple_retries(self):
        # Three invalid attempts, then valid

        """WHEN entering multiple invalid values then a valid option"""
        result = _run_select("0\n5\nabc\n2\n")

        """THEN the valid follow-up selection is returned"""
        assert result.exit_code == 0
        assert "RESULT:b" in result.output


class TestSelectOneMessages:
    """Scenarios for select_one error messages."""

    """GIVEN a three-choice menu"""

    def test_out_of_range_message(self):
        """WHEN entering an out-of-range number"""
        result = _run_select("6\n1\n")

        """THEN the error mentions the option is not available"""
        assert "Option 6 is not available" in result.output or "not available" in result.output

    """GIVEN a three-choice menu"""

    def test_range_mentioned_in_error(self):
        """WHEN entering an out-of-range number"""
        result = _run_select("6\n1\n")

        """THEN the error includes the valid range"""
        assert "1 to 3" in result.output

    """GIVEN a three-choice menu"""

    def test_non_numeric_message(self):
        """WHEN entering non-numeric text"""
        result = _run_select("xyz\n1\n")

        """THEN the error says 'Invalid input'"""
        assert "Invalid input" in result.output

    """GIVEN a three-choice menu"""

    def test_range_in_non_numeric_error(self):
        """WHEN entering non-numeric text"""
        result = _run_select("xyz\n1\n")

        """THEN the error includes the valid range"""
        assert "1 to 3" in result.output


class TestSelectOneRedisplay:
    """Scenarios for select_one choice redisplay."""

    """GIVEN a three-choice menu"""

    def test_choices_shown_after_error(self):
        """WHEN entering an invalid option then a valid one"""
        result = _run_select("5\n1\n")

        """THEN the menu is displayed at least twice"""
        # The menu should appear at least twice (initial + after error)
        assert result.output.count("Option A") >= 2

    """GIVEN a three-choice menu"""

    def test_choices_shown_with_numbers(self):
        """WHEN the menu is displayed"""
        result = _run_select("1\n")

        """THEN each choice is shown with its number"""
        assert "[1]" in result.output
        assert "[2]" in result.output
        assert "[3]" in result.output

    """GIVEN a three-choice menu with a default"""

    def test_default_marker_shown(self):
        """WHEN the menu is displayed"""
        result = _run_select("1\n")

        """THEN the default marker is visible"""
        assert "default" in result.output.lower()

    """GIVEN a menu with a custom hint"""

    def test_hint_displayed(self):
        """WHEN the menu is displayed"""
        result = _run_select("1\n", hint="Pick one carefully")

        """THEN the hint text is shown"""
        assert "Pick one carefully" in result.output
