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
from datetime import date, timedelta
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


# ── select_one: valid input ─────────────────────────────────────────────────


class TestSelectOneValid:
    """Scenarios for valid select_one input."""

    def test_first_option(self):
        """GIVEN a three-choice menu."""
        result = _run_select("1\n")

        """WHEN selecting option 1."""

        """THEN the first value is returned."""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    def test_second_option(self):
        """GIVEN a three-choice menu."""
        result = _run_select("2\n")

        """WHEN selecting option 2."""

        """THEN the second value is returned."""
        assert result.exit_code == 0
        assert "RESULT:b" in result.output

    def test_third_option(self):
        """GIVEN a three-choice menu."""
        result = _run_select("3\n")

        """WHEN selecting option 3."""

        """THEN the third value is returned."""
        assert result.exit_code == 0
        assert "RESULT:c" in result.output

    def test_default_on_enter(self):
        """GIVEN a three-choice menu with default index 0."""
        # Empty input → default (index 0 → "a")

        """WHEN pressing Enter without input."""
        result = _run_select("\n")

        """THEN the default value is returned."""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    def test_custom_default_index(self):
        """GIVEN a menu with default_index=2."""
        # Default index 2 → "c"

        """WHEN pressing Enter."""
        result = _run_select("\n", default_index=2)

        """THEN the third option is returned."""
        assert result.exit_code == 0
        assert "RESULT:c" in result.output

    def test_single_choice_menu(self):
        """GIVEN a single-choice menu."""

        """WHEN selecting option 1."""
        result = _run_select("1\n", choices=[("Only option", "only")])

        """THEN the only value is returned."""
        assert result.exit_code == 0
        assert "RESULT:only" in result.output

    def test_single_choice_default(self):
        """GIVEN a single-choice menu."""

        """WHEN pressing Enter."""
        result = _run_select("\n", choices=[("Only option", "only")])

        """THEN the only value is returned."""
        assert result.exit_code == 0
        assert "RESULT:only" in result.output


# ── select_one: invalid input ───────────────────────────────────────────────


class TestSelectOneInvalid:
    """Scenarios for invalid select_one input."""

    def test_out_of_range_high(self):
        """GIVEN a three-choice menu."""
        # 4 is out of range for 3 choices → error, then valid "2"

        """WHEN entering 4 then a valid option."""
        result = _run_select("4\n2\n")

        """THEN the valid follow-up selection is returned."""
        assert result.exit_code == 0
        assert "RESULT:b" in result.output

    def test_out_of_range_very_high(self):
        """GIVEN a three-choice menu."""

        """WHEN entering 99 then a valid option."""
        result = _run_select("99\n1\n")

        """THEN the valid follow-up selection is returned."""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    def test_zero_rejected(self):
        """GIVEN a three-choice menu."""

        """WHEN entering 0 then a valid option."""
        result = _run_select("0\n3\n")

        """THEN the valid follow-up selection is returned."""
        assert result.exit_code == 0
        assert "RESULT:c" in result.output

    def test_negative_rejected(self):
        """GIVEN a three-choice menu."""

        """WHEN entering -1 then a valid option."""
        result = _run_select("-1\n1\n")

        """THEN the valid follow-up selection is returned."""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    def test_non_numeric_rejected(self):
        """GIVEN a three-choice menu."""

        """WHEN entering non-numeric text then a valid option."""
        result = _run_select("abc\n2\n")

        """THEN the valid follow-up selection is returned."""
        assert result.exit_code == 0
        assert "RESULT:b" in result.output

    def test_float_rejected(self):
        """GIVEN a three-choice menu."""

        """WHEN entering a float then a valid option."""
        result = _run_select("1.5\n1\n")

        """THEN the valid follow-up selection is returned."""
        assert result.exit_code == 0
        assert "RESULT:a" in result.output

    def test_special_chars_rejected(self):
        """GIVEN a three-choice menu."""

        """WHEN entering special characters then a valid option."""
        result = _run_select("@#$\n3\n")

        """THEN the valid follow-up selection is returned."""
        assert result.exit_code == 0
        assert "RESULT:c" in result.output

    def test_multiple_retries(self):
        """GIVEN a three-choice menu."""
        # Three invalid attempts, then valid

        """WHEN entering multiple invalid values then a valid option."""
        result = _run_select("0\n5\nabc\n2\n")

        """THEN the valid follow-up selection is returned."""
        assert result.exit_code == 0
        assert "RESULT:b" in result.output


# ── select_one: error messages ──────────────────────────────────────────────


class TestSelectOneMessages:
    """Scenarios for select_one error messages."""

    def test_out_of_range_message(self):
        """GIVEN a three-choice menu."""

        """WHEN entering an out-of-range number."""
        result = _run_select("6\n1\n")

        """THEN the error mentions the option is not available."""
        assert "Option 6 is not available" in result.output or "not available" in result.output

    def test_range_mentioned_in_error(self):
        """GIVEN a three-choice menu."""

        """WHEN entering an out-of-range number."""
        result = _run_select("6\n1\n")

        """THEN the error includes the valid range."""
        assert "1 to 3" in result.output

    def test_non_numeric_message(self):
        """GIVEN a three-choice menu."""

        """WHEN entering non-numeric text."""
        result = _run_select("xyz\n1\n")

        """THEN the error says 'Invalid input'."""
        assert "Invalid input" in result.output

    def test_range_in_non_numeric_error(self):
        """GIVEN a three-choice menu."""

        """WHEN entering non-numeric text."""
        result = _run_select("xyz\n1\n")

        """THEN the error includes the valid range."""
        assert "1 to 3" in result.output


# ── select_one: re-display choices ──────────────────────────────────────────


class TestSelectOneRedisplay:
    """Scenarios for select_one choice redisplay."""

    def test_choices_shown_after_error(self):
        """GIVEN a three-choice menu."""

        """WHEN entering an invalid option then a valid one."""
        result = _run_select("5\n1\n")

        """THEN the menu is displayed at least twice."""
        # The menu should appear at least twice (initial + after error)
        assert result.output.count("Option A") >= 2

    def test_choices_shown_with_numbers(self):
        """GIVEN a three-choice menu."""

        """WHEN the menu is displayed."""
        result = _run_select("1\n")

        """THEN each choice is shown with its number."""
        assert "[1]" in result.output
        assert "[2]" in result.output
        assert "[3]" in result.output

    def test_default_marker_shown(self):
        """GIVEN a three-choice menu with a default."""

        """WHEN the menu is displayed."""
        result = _run_select("1\n")

        """THEN the default marker is visible."""
        assert "default" in result.output.lower()

    def test_hint_displayed(self):
        """GIVEN a menu with a custom hint."""

        """WHEN the menu is displayed."""
        result = _run_select("1\n", hint="Pick one carefully")

        """THEN the hint text is shown."""
        assert "Pick one carefully" in result.output


# ── confirm ─────────────────────────────────────────────────────────────────


class TestConfirm:
    """Scenarios for confirm prompts."""

    def test_yes(self):
        """GIVEN a confirm prompt."""

        """WHEN answering 'y'."""
        result = _run_confirm("y\n")

        """THEN True is returned."""
        assert result.exit_code == 0
        assert "RESULT:True" in result.output

    def test_no(self):
        """GIVEN a confirm prompt."""

        """WHEN answering 'n'."""
        result = _run_confirm("n\n")

        """THEN False is returned."""
        assert result.exit_code == 0
        assert "RESULT:False" in result.output

    def test_default_false(self):
        """GIVEN a confirm prompt with default=False."""

        """WHEN pressing Enter without input."""
        result = _run_confirm("\n", default=False)

        """THEN False is returned."""
        assert result.exit_code == 0
        assert "RESULT:False" in result.output

    def test_default_true(self):
        """GIVEN a confirm prompt with default=True."""

        """WHEN pressing Enter without input."""
        result = _run_confirm("\n", default=True)

        """THEN True is returned."""
        assert result.exit_code == 0
        assert "RESULT:True" in result.output


# ── text_prompt ─────────────────────────────────────────────────────────────


class TestTextPrompt:
    """Scenarios for text prompts."""

    def test_returns_input(self):
        """GIVEN a text prompt."""

        """WHEN entering 'hello world'."""
        result = _run_text_prompt("hello world\n")

        """THEN the entered text is returned."""
        assert result.exit_code == 0
        assert "RESULT:hello world" in result.output

    def test_default_on_empty(self):
        """GIVEN a text prompt with default='fallback'."""

        """WHEN pressing Enter without input."""
        result = _run_text_prompt("\n", default="fallback")

        """THEN the default value is returned."""
        assert result.exit_code == 0
        assert "RESULT:fallback" in result.output


# ── Default value alignment ─────────────────────────────────────────────────


class TestDefaultAlignment:
    """Scenarios for default value alignment."""

    def test_int_value_default(self):
        """GIVEN choices with integer values and default_index=2."""
        choices = [("Seven", 7), ("Fourteen", 14), ("Thirty", 30)]

        """WHEN pressing Enter."""
        result = _run_select("\n", choices=choices, default_index=2)

        """THEN the integer value at the default index is returned."""
        assert result.exit_code == 0
        assert "RESULT:30" in result.output

    def test_string_value_default(self):
        """GIVEN choices with string values and default_index=1."""
        choices = [("PDF file", "pdf"), ("Word doc", "docx")]

        """WHEN pressing Enter."""
        result = _run_select("\n", choices=choices, default_index=1)

        """THEN the string value at the default index is returned."""
        assert result.exit_code == 0
        assert "RESULT:docx" in result.output

    def test_enum_value_default(self):
        """GIVEN choices with enum values and default_index=2."""
        from releasepilot.domain.enums import Audience

        choices = [
            ("Changelog", Audience.CHANGELOG),
            ("User", Audience.USER),
            ("Executive", Audience.EXECUTIVE),
        ]

        """WHEN pressing Enter."""
        result = _run_select("\n", choices=choices, default_index=2)

        """THEN the enum value at the default index is returned."""
        assert result.exit_code == 0
        assert "executive" in result.output.lower()

    def test_mixed_type_values(self):
        """GIVEN choices with mixed int/string values and default_index=1."""
        choices: list[tuple[str, int | str]] = [
            ("Last 7 days", 7),
            ("Last 30 days", 30),
            ("Custom date", "custom"),
        ]

        """WHEN pressing Enter."""
        result = _run_select("\n", choices=choices, default_index=1)

        """THEN the value at the default index is returned."""
        assert result.exit_code == 0
        assert "RESULT:30" in result.output

    def test_guide_time_range_choices_defaults_work(self):
        """GIVEN the exact time range choices from guide.py."""
        from releasepilot.cli.guide import _TIME_RANGE_CHOICES

        """WHEN pressing Enter with default_index=2."""
        result = _run_select("\n", choices=_TIME_RANGE_CHOICES, default_index=2)

        """THEN the default value is returned without crashing."""
        assert result.exit_code == 0
        assert "RESULT:30" in result.output

    def test_guide_audience_choices_defaults_work(self):
        """GIVEN the exact audience choices from guide.py."""
        from releasepilot.cli.guide import _AUDIENCE_CHOICES

        """WHEN pressing Enter with default_index=0."""
        result = _run_select("\n", choices=_AUDIENCE_CHOICES, default_index=0)

        """THEN the default value is returned without crashing."""
        assert result.exit_code == 0
        assert "changelog" in result.output.lower()

    def test_guide_format_choices_defaults_work(self):
        """GIVEN the exact format choices from guide.py."""
        from releasepilot.cli.guide import _FORMAT_CHOICES

        """WHEN pressing Enter with default_index=0."""
        result = _run_select("\n", choices=_FORMAT_CHOICES, default_index=0)

        """THEN the default value is returned without crashing."""
        assert result.exit_code == 0
        assert "markdown" in result.output.lower()

    def test_guide_exec_format_choices_defaults_work(self):
        """GIVEN the exact executive format choices from guide.py."""
        from releasepilot.cli.guide import _FORMAT_CHOICES_EXECUTIVE

        """WHEN pressing Enter with default_index=0."""
        result = _run_select("\n", choices=_FORMAT_CHOICES_EXECUTIVE, default_index=0)

        """THEN the default value is returned without crashing."""
        assert result.exit_code == 0
        assert "RESULT:pdf" in result.output

    def test_invalid_default_index_falls_back(self):
        """GIVEN a menu with an out-of-range default_index=99."""

        """WHEN pressing Enter."""
        result = _run_select("\n", choices=_SAMPLE_CHOICES, default_index=99)

        """THEN the index is clamped to the last valid item."""
        assert result.exit_code == 0
        # Clamped to max valid index (last item)
        assert "RESULT:c" in result.output


def _init_repo(path: Path) -> None:
    """Create a git repo with realistic commits for guide tests."""
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@t.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "T"],
        check=True, capture_output=True,
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
            check=True, capture_output=True,
        )


class TestGuideValidation:
    """Scenarios for guided workflow validation."""

    def test_invalid_audience_then_valid(self, tmp_path: Path):
        """GIVEN a git repo and the guided workflow."""
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN entering an invalid audience choice then a valid one."""
        # Flow: branch=1(main), time=3(30d), audience=9(invalid)→1(valid), format=1(md),
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="1\n3\n9\n1\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully."""
        assert result.exit_code == 0

    def test_invalid_time_range_then_valid(self, tmp_path: Path):
        """GIVEN a git repo and the guided workflow."""
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN entering an invalid time range then a valid one."""
        # Flow: branch=1(main), time=9(invalid)→2(14d), audience=1, format=1,
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="1\n9\n2\n1\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully."""
        assert result.exit_code == 0

    def test_invalid_format_then_valid(self, tmp_path: Path):
        """GIVEN a git repo and the guided workflow."""
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN entering an invalid format choice then a valid one."""
        # Flow: branch=1(main), time=3, audience=1, format=5(invalid)→1(valid),
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="1\n3\n1\n5\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully."""
        assert result.exit_code == 0

    def test_non_numeric_audience_then_valid(self, tmp_path: Path):
        """GIVEN a git repo and the guided workflow."""
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN entering non-numeric audience input then a valid one."""
        # Flow: branch=1(main), time=3, audience=abc(invalid)→2(valid), format=1,
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="1\n3\nabc\n2\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully."""
        assert result.exit_code == 0

    def test_happy_path_all_defaults(self, tmp_path: Path):
        """GIVEN a git repo and the guided workflow."""
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN pressing Enter through every step."""
        # Flow: branch=default, time=default, audience=default, format=default,
        # app_name=(empty), language=default, save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="\n\n\n\n\n\nn\n",
        )

        """THEN the workflow completes successfully."""
        assert result.exit_code == 0

    def test_custom_date_range(self, tmp_path: Path):
        """GIVEN a git repo and the guided workflow."""
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()
        custom_date = (date.today() - timedelta(days=60)).isoformat()

        """WHEN selecting 'Custom date range' and entering a date."""
        # Flow: branch=1, time=6(custom)→date, audience=1, format=1,
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input=f"1\n6\n{custom_date}\n1\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully."""
        assert result.exit_code == 0

    def test_branch_other_manual(self, tmp_path: Path):
        """GIVEN a git repo and the guided workflow."""
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN selecting 'Other' in the branch menu and typing a branch name."""
        # Flow: branch=2(Other)→"main", time=3, audience=1, format=1,
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="2\nmain\n3\n1\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully."""
        assert result.exit_code == 0
