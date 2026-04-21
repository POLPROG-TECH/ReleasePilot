"""Reusable interactive prompt components for the guided workflow.

Centralises all interactive selection logic so that:
- Choice validation is strict and consistent across every guided step
- Arrow-key navigation (via questionary) is available in real terminals
- A validated numeric fallback works in non-TTY environments (tests, CI)
- Re-prompting on invalid input is the default behaviour

Architecture:
    select_one()   - menu selection (arrow-key or numeric)
    confirm()      - yes/no question
    text_prompt()  - free-form text input

When questionary is importable *and* stdin is a TTY, arrow-key mode is used.
Otherwise the numeric/click fallback is used.  Both paths validate strictly.
"""

from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Feature detection
# ---------------------------------------------------------------------------


def _use_arrow_keys() -> bool:
    """Return True if arrow-key prompts (questionary) should be used."""
    if not sys.stdin.isatty():
        return False
    try:
        import questionary  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_one[T](
    title: str,
    choices: list[tuple[str, T]],
    *,
    default_index: int = 0,
    hint: str | None = None,
) -> T:
    """Present a selection menu and return the chosen value.

    Args:
        title: Menu heading displayed above the choices.
        choices: Ordered list of ``(label, value)`` pairs.
        default_index: Zero-based index of the pre-selected default.
            Clamped to the valid range if out of bounds.
        hint: Optional subtitle shown below the title.

    Returns:
        The *value* element of the selected ``(label, value)`` pair.

    In a real TTY with questionary installed the user navigates with
    ↑/↓ arrows and confirms with Enter.  Otherwise a validated numeric
    prompt is shown with re-prompt on any invalid input.
    """
    # Clamp default_index so an out-of-range value never crashes
    if not choices:
        msg = "select_one() requires at least one choice"
        raise ValueError(msg)
    default_index = max(0, min(default_index, len(choices) - 1))

    if _use_arrow_keys():
        return _questionary_select(title, choices, default_index, hint)
    return _numeric_select(title, choices, default_index, hint)


def confirm(message: str, *, default: bool = False) -> bool:
    """Ask a yes/no question.

    Uses questionary in TTY mode, click.confirm otherwise.
    """
    if _use_arrow_keys():
        import questionary

        result = questionary.confirm(message, default=default).ask()
        if result is None:
            raise SystemExit(130)
        return result
    return click.confirm(message, default=default)


def text_prompt(message: str, *, default: str = "") -> str:
    """Prompt for free-form text input.

    Uses questionary in TTY mode, click.prompt otherwise.
    """
    if _use_arrow_keys():
        import questionary

        result = questionary.text(message, default=default).ask()
        if result is None:
            raise SystemExit(130)
        return result
    return click.prompt(message, default=default, show_default=bool(default))


# ---------------------------------------------------------------------------
# Questionary (arrow-key) implementation
# ---------------------------------------------------------------------------


def _questionary_select[T](
    title: str,
    choices: list[tuple[str, T]],
    default_index: int,
    hint: str | None,
) -> T:
    """Arrow-key selection via questionary."""
    import questionary
    from questionary import Choice, Style

    style = Style(
        [
            ("qmark", "fg:cyan bold"),
            ("question", "bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
            ("selected", "fg:green"),
            ("instruction", ""),
        ]
    )

    q_choices = [Choice(title=label, value=value) for label, value in choices]

    # questionary matches `default` against Choice.value, not Choice.title.
    # Pass the value and fall back gracefully if it doesn't match.
    default_value = choices[default_index][1] if 0 <= default_index < len(choices) else None

    try:
        question = questionary.select(
            title,
            choices=q_choices,
            default=default_value,
            instruction=hint or "(↑↓ to move, Enter to select)",
            style=style,
        )
    except ValueError:
        # Default didn't match any choice value - retry without a default
        question = questionary.select(
            title,
            choices=q_choices,
            instruction=hint or "(↑↓ to move, Enter to select)",
            style=style,
        )

    result = question.ask()

    if result is None:
        raise SystemExit(130)

    return result


# ---------------------------------------------------------------------------
# Numeric-fallback implementation
# ---------------------------------------------------------------------------


def _display_menu(
    title: str,
    choices: list[tuple[str, ...]],
    default_num: int,
    hint: str | None,
) -> None:
    """Render a numbered menu to the Rich console."""
    console.print(f"[bold]{title}[/bold]")
    if hint:
        console.print(f"   [dim]{hint}[/dim]")
    console.print()
    for i, (label, *_) in enumerate(choices, 1):
        marker = " [green](default)[/green]" if i == default_num else ""
        console.print(f"   [{i}] {label}{marker}")
    console.print()


def _numeric_select[T](
    title: str,
    choices: list[tuple[str, T]],
    default_index: int,
    hint: str | None,
) -> T:
    """Validated numeric selection with re-prompt on invalid input."""
    max_num = len(choices)
    default_num = default_index + 1

    _display_menu(title, choices, default_num, hint)

    while True:
        try:
            raw = click.prompt(
                "Choice",
                default=str(default_num),
                show_default=False,
            )
        except (click.Abort, EOFError) as exc:
            raise SystemExit(130) from exc

        raw = str(raw).strip()

        # Validate: must be an integer
        try:
            num = int(raw)
        except ValueError:
            console.print(
                f"[yellow]  ⚠ Invalid input. Please enter a number from 1 to {max_num}.[/yellow]",
            )
            console.print()
            _display_menu(title, choices, default_num, hint)
            continue

        # Validate: must be in range
        if 1 <= num <= max_num:
            return choices[num - 1][1]

        console.print(
            f"[yellow]  ⚠ Option {num} is not available. "
            f"Please enter a number from 1 to {max_num}.[/yellow]",
        )
        console.print()
        _display_menu(title, choices, default_num, hint)
