"""Rendering package for ReleasePilot."""

__all__ = ["REPO_URL", "AUTHOR", "TOOL_NAME", "footer_text"]

REPO_URL = "https://github.com/polprog-tech/ReleasePilot"
AUTHOR = "POLPROG"
TOOL_NAME = "ReleasePilot"


def footer_text(*, include_url: bool = False, lang: str = "en") -> str:
    """Return a consistent footer string with date/time and attribution.

    When *include_url* is True the raw URL is appended (for plain-text / markdown).
    Binary renderers (PDF/DOCX) should set include_url=False and create a
    clickable hyperlink on the author name instead.
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    from releasepilot.i18n import get_label

    tpl = get_label("footer_generated", lang)
    base = tpl.format(tool=TOOL_NAME, author=AUTHOR, datetime=now)
    if include_url:
        base += f" · {REPO_URL}"
    return base
