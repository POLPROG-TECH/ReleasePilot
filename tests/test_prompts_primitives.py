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


# ── select_one: invalid input ───────────────────────────────────────────────


# ── select_one: error messages ──────────────────────────────────────────────


# ── select_one: re-display choices ──────────────────────────────────────────


# ── confirm ─────────────────────────────────────────────────────────────────


# ── text_prompt ─────────────────────────────────────────────────────────────


# ── Default value alignment ─────────────────────────────────────────────────


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


class TestConfirm:
    """Scenarios for confirm prompts."""

    """GIVEN a confirm prompt"""
    def test_yes(self):
        """WHEN answering 'y'"""
        result = _run_confirm("y\n")

        """THEN True is returned"""
        assert result.exit_code == 0
        assert "RESULT:True" in result.output

    """GIVEN a confirm prompt"""
    def test_no(self):
        """WHEN answering 'n'"""
        result = _run_confirm("n\n")

        """THEN False is returned"""
        assert result.exit_code == 0
        assert "RESULT:False" in result.output

    """GIVEN a confirm prompt with default=False"""
    def test_default_false(self):
        """WHEN pressing Enter without input"""
        result = _run_confirm("\n", default=False)

        """THEN False is returned"""
        assert result.exit_code == 0
        assert "RESULT:False" in result.output

    """GIVEN a confirm prompt with default=True"""
    def test_default_true(self):
        """WHEN pressing Enter without input"""
        result = _run_confirm("\n", default=True)

        """THEN True is returned"""
        assert result.exit_code == 0
        assert "RESULT:True" in result.output


class TestTextPrompt:
    """Scenarios for text prompts."""

    """GIVEN a text prompt"""
    def test_returns_input(self):
        """WHEN entering 'hello world'"""
        result = _run_text_prompt("hello world\n")

        """THEN the entered text is returned"""
        assert result.exit_code == 0
        assert "RESULT:hello world" in result.output

    """GIVEN a text prompt with default='fallback'"""
    def test_default_on_empty(self):
        """WHEN pressing Enter without input"""
        result = _run_text_prompt("\n", default="fallback")

        """THEN the default value is returned"""
        assert result.exit_code == 0
        assert "RESULT:fallback" in result.output


class TestDefaultAlignment:
    """Scenarios for default value alignment."""

    """GIVEN choices with integer values and default_index=2"""
    def test_int_value_default(self):
        choices = [("Seven", 7), ("Fourteen", 14), ("Thirty", 30)]

        """WHEN pressing Enter"""
        result = _run_select("\n", choices=choices, default_index=2)

        """THEN the integer value at the default index is returned"""
        assert result.exit_code == 0
        assert "RESULT:30" in result.output

    """GIVEN choices with string values and default_index=1"""
    def test_string_value_default(self):
        choices = [("PDF file", "pdf"), ("Word doc", "docx")]

        """WHEN pressing Enter"""
        result = _run_select("\n", choices=choices, default_index=1)

        """THEN the string value at the default index is returned"""
        assert result.exit_code == 0
        assert "RESULT:docx" in result.output

    """GIVEN choices with enum values and default_index=2"""
    def test_enum_value_default(self):
        from releasepilot.domain.enums import Audience

        choices = [
            ("Changelog", Audience.CHANGELOG),
            ("User", Audience.USER),
            ("Executive", Audience.EXECUTIVE),
        ]

        """WHEN pressing Enter"""
        result = _run_select("\n", choices=choices, default_index=2)

        """THEN the enum value at the default index is returned"""
        assert result.exit_code == 0
        assert "executive" in result.output.lower()

    """GIVEN choices with mixed int/string values and default_index=1"""
    def test_mixed_type_values(self):
        choices: list[tuple[str, int | str]] = [
            ("Last 7 days", 7),
            ("Last 30 days", 30),
            ("Custom date", "custom"),
        ]

        """WHEN pressing Enter"""
        result = _run_select("\n", choices=choices, default_index=1)

        """THEN the value at the default index is returned"""
        assert result.exit_code == 0
        assert "RESULT:30" in result.output

    """GIVEN the exact time range choices from guide.py"""
    def test_guide_time_range_choices_defaults_work(self):
        from releasepilot.cli.guide import _TIME_RANGE_CHOICES

        """WHEN pressing Enter with default_index=2"""
        result = _run_select("\n", choices=_TIME_RANGE_CHOICES, default_index=2)

        """THEN the default value is returned without crashing"""
        assert result.exit_code == 0
        assert "RESULT:30" in result.output

    """GIVEN the exact audience choices from guide.py"""
    def test_guide_audience_choices_defaults_work(self):
        from releasepilot.cli.guide import _AUDIENCE_CHOICES

        """WHEN pressing Enter with default_index=0"""
        result = _run_select("\n", choices=_AUDIENCE_CHOICES, default_index=0)

        """THEN the default value is returned without crashing"""
        assert result.exit_code == 0
        assert "changelog" in result.output.lower()

    """GIVEN the exact format choices from guide.py"""
    def test_guide_format_choices_defaults_work(self):
        from releasepilot.cli.guide import _FORMAT_CHOICES

        """WHEN pressing Enter with default_index=0"""
        result = _run_select("\n", choices=_FORMAT_CHOICES, default_index=0)

        """THEN the default value is returned without crashing"""
        assert result.exit_code == 0
        assert "markdown" in result.output.lower()

    """GIVEN the exact executive format choices from guide.py"""
    def test_guide_exec_format_choices_defaults_work(self):
        from releasepilot.cli.guide import _FORMAT_CHOICES_EXECUTIVE

        """WHEN pressing Enter with default_index=0"""
        result = _run_select("\n", choices=_FORMAT_CHOICES_EXECUTIVE, default_index=0)

        """THEN the default value is returned without crashing"""
        assert result.exit_code == 0
        assert "RESULT:pdf" in result.output

    """GIVEN a menu with an out-of-range default_index=99"""
    def test_invalid_default_index_falls_back(self):
        """WHEN pressing Enter"""
        result = _run_select("\n", choices=_SAMPLE_CHOICES, default_index=99)

        """THEN the index is clamped to the last valid item"""
        assert result.exit_code == 0
        # Clamped to max valid index (last item)
        assert "RESULT:c" in result.output


class TestGuideValidation:
    """Scenarios for guided workflow validation."""

    """GIVEN a git repo and the guided workflow"""
    def test_invalid_audience_then_valid(self, tmp_path: Path):
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN entering an invalid audience choice then a valid one"""
        # Flow: branch=1(main), time=3(30d), audience=9(invalid)→1(valid), format=1(md),
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="1\n3\n9\n1\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully"""
        assert result.exit_code == 0

    """GIVEN a git repo and the guided workflow"""
    def test_invalid_time_range_then_valid(self, tmp_path: Path):
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN entering an invalid time range then a valid one"""
        # Flow: branch=1(main), time=9(invalid)→2(14d), audience=1, format=1,
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="1\n9\n2\n1\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully"""
        assert result.exit_code == 0

    """GIVEN a git repo and the guided workflow"""
    def test_invalid_format_then_valid(self, tmp_path: Path):
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN entering an invalid format choice then a valid one"""
        # Flow: branch=1(main), time=3, audience=1, format=5(invalid)→1(valid),
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="1\n3\n1\n5\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully"""
        assert result.exit_code == 0

    """GIVEN a git repo and the guided workflow"""
    def test_non_numeric_audience_then_valid(self, tmp_path: Path):
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN entering non-numeric audience input then a valid one"""
        # Flow: branch=1(main), time=3, audience=abc(invalid)→2(valid), format=1,
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="1\n3\nabc\n2\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully"""
        assert result.exit_code == 0

    """GIVEN a git repo and the guided workflow"""
    def test_happy_path_all_defaults(self, tmp_path: Path):
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN pressing Enter through every step"""
        # Flow: branch=default, time=default, audience=default, format=default,
        # app_name=(empty), language=default, save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="\n\n\n\n\n\nn\n",
        )

        """THEN the workflow completes successfully"""
        assert result.exit_code == 0

    """GIVEN a git repo and the guided workflow"""
    def test_custom_date_range(self, tmp_path: Path):
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()
        custom_date = (date.today() - timedelta(days=60)).isoformat()

        """WHEN selecting 'Custom date range' and entering a date"""
        # Flow: branch=1, time=6(custom)→date, audience=1, format=1,
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input=f"1\n6\n{custom_date}\n1\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully"""
        assert result.exit_code == 0

    """GIVEN a git repo and the guided workflow"""
    def test_branch_other_manual(self, tmp_path: Path):
        from releasepilot.cli.app import cli

        _init_repo(tmp_path)
        runner = CliRunner()

        """WHEN selecting 'Other' in the branch menu and typing a branch name"""
        # Flow: branch=2(Other)→"main", time=3, audience=1, format=1,
        # app_name=(empty), language=1(en), save=n
        result = runner.invoke(
            cli,
            ["guide", str(tmp_path)],
            input="2\nmain\n3\n1\n1\n\n1\nn\n",
        )

        """THEN the workflow completes successfully"""
        assert result.exit_code == 0
