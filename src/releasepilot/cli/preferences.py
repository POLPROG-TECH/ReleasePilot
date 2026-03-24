"""Smart defaults for guided workflow based on repeated usage.

Stores choice frequency in ~/.config/releasepilot/preferences.json.
After a choice is selected 3+ times for a given prompt, it becomes
the new default. Set RELEASEPILOT_NO_PREFS=1 to disable.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

PREFS_DIR = Path.home() / ".config" / "releasepilot"
PREFS_FILE = PREFS_DIR / "preferences.json"
PROMOTION_THRESHOLD = 3  # How many times before a choice becomes default


def record_choice(prompt_key: str, choice_value: str) -> None:
    """Record that the user chose *choice_value* for prompt *prompt_key*."""
    if _is_disabled():
        return

    data = _load()
    bucket = data.setdefault(prompt_key, {})
    bucket[choice_value] = bucket.get(choice_value, 0) + 1
    _save(data)


def get_preferred_default(prompt_key: str, choices: list[tuple[str, ...]]) -> int | None:
    """Return the preferred default index for a prompt, or ``None``.

    Returns the index into *choices* if a preference has been promoted
    (used >= PROMOTION_THRESHOLD times) **and** the preferred value still
    exists in the current choices list.  Each element of *choices* is a
    tuple whose second element is the value to match against.
    """
    if _is_disabled():
        return None

    data = _load()
    bucket = data.get(prompt_key)
    if not bucket:
        return None

    # Find the choice with the highest count that meets the threshold.
    best_value: str | None = None
    best_count = 0
    for value, count in bucket.items():
        if count >= PROMOTION_THRESHOLD and count > best_count:
            best_value = value
            best_count = count

    if best_value is None:
        return None

    # Match against str(value) of each choice tuple.
    for idx, choice in enumerate(choices):
        if str(choice[1]) == best_value:
            return idx

    return None


def reset_preferences() -> None:
    """Delete all saved preferences."""
    with contextlib.suppress(OSError):
        PREFS_FILE.unlink(missing_ok=True)


def _load() -> dict:
    """Load preferences from disk. Returns empty dict on any error."""
    try:
        return json.loads(PREFS_FILE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _save(data: dict) -> None:
    """Save preferences to disk atomically.

    Writes to a temporary file first and then renames to avoid corruption
    if the process is interrupted mid-write.
    """
    try:
        PREFS_DIR.mkdir(parents=True, exist_ok=True)
        import tempfile

        fd, tmp_path = tempfile.mkstemp(
            dir=str(PREFS_DIR),
            suffix=".tmp",
            prefix=".prefs-",
        )
        closed = False
        try:
            os.write(fd, (json.dumps(data, indent=2) + "\n").encode("utf-8"))
            os.close(fd)
            closed = True
            os.replace(tmp_path, PREFS_FILE)
        except BaseException:
            if not closed:
                with contextlib.suppress(OSError):
                    os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except OSError:
        pass


def _is_disabled() -> bool:
    """Return True if preferences are disabled via env var."""
    return os.environ.get("RELEASEPILOT_NO_PREFS", "") == "1"
