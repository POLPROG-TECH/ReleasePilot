"""ReleasePilot CLI — entry point.

Defines the Click group and registers all command submodules.
"""

from __future__ import annotations

import contextlib
import logging
import signal

import click

from releasepilot import __version__

# Re-export constants and console so existing imports from app.py keep working.
from releasepilot.cli.helpers import (  # noqa: F401
    _ALL_AUDIENCES,
    _ALL_FORMATS,
    _atomic_write_bytes,
    _atomic_write_text,
    _build_settings,
    _common_options,
    _handle_error,
    _is_empty_release,
    _make_cli_progress,
    _run_dry,
    _run_pipeline,
    _SuppressOs,
    console,
)

# ── Signal handling ─────────────────────────────────────────────────────────


def _install_signal_handlers() -> None:
    """Install graceful signal handlers so Ctrl-C exits cleanly."""

    def _handler(signum: int, _frame: object) -> None:
        sig_name = signal.Signals(signum).name
        console.print(f"\n[yellow]Interrupted ({sig_name}). Exiting.[/yellow]")
        raise SystemExit(128 + signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(OSError, ValueError):
            signal.signal(sig, _handler)


# ── CLI Group ────────────────────────────────────────────────────────────────


@click.group()
@click.version_option(__version__, prog_name="releasepilot")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable verbose/debug logging")
def cli(verbose: bool):
    """ReleasePilot — Generate polished release notes from your repository."""
    _install_signal_handlers()
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(name)s %(levelname)s: %(message)s",
    )


# ── Entry point ──────────────────────────────────────────────────────────────


def main():
    cli()


# Register command submodules (must come after ``cli`` is defined).
import releasepilot.cli.cmd_dashboard  # noqa: F401, E402
import releasepilot.cli.cmd_export  # noqa: F401, E402
import releasepilot.cli.cmd_generate  # noqa: F401, E402
import releasepilot.cli.cmd_inspect  # noqa: F401, E402
import releasepilot.cli.cmd_multi  # noqa: F401, E402
