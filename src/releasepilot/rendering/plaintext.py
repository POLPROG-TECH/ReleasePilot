"""Plain text renderer.

Produces clean terminal-friendly output for quick review.
"""

from __future__ import annotations

from releasepilot.config.settings import RenderConfig
from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import ChangeGroup, ReleaseNotes


class PlaintextRenderer:
    """Renders ReleaseNotes as plain text for terminal display."""

    def render(self, notes: ReleaseNotes, config: RenderConfig) -> str:
        if notes.is_empty:
            title = notes.release_range.display_title
            return f"{title}\n{'=' * len(title)}\n\nNo notable changes in this release.\n"

        parts: list[str] = []
        parts.append(_render_header(notes))

        if notes.breaking_changes:
            parts.append("BREAKING CHANGES:")
            for item in notes.breaking_changes:
                parts.append(f"  ! {item.title}")
            parts.append("")

        for group in notes.groups:
            if notes.breaking_changes and group.category == ChangeCategory.BREAKING:
                continue
            rendered = _render_group(group, config)
            if rendered:
                parts.append(rendered)

        parts.append(f"({notes.total_changes} changes)")
        return "\n".join(parts)


def _render_header(notes: ReleaseNotes) -> str:
    title = notes.release_range.display_title
    sep = "=" * len(title)
    lines = [title, sep]

    if notes.release_range.release_date:
        lines.append(f"Released: {notes.release_range.release_date.isoformat()}")

    lines.append("")
    return "\n".join(lines)


def _render_group(group: ChangeGroup, config: RenderConfig) -> str:
    if not group.items:
        return ""

    # Strip emoji from display label for terminal
    label = group.display_label
    for emoji_char in "⚠️🔒✨🔧🐛⚡📦📝🏗️♻️📋":
        label = label.replace(emoji_char, "").strip()

    items = group.items
    if config.max_items_per_group > 0:
        items = items[: config.max_items_per_group]

    lines = [f"{label}:"]
    for item in items:
        scope_prefix = f"[{item.scope}] " if config.show_scope and item.scope else ""
        lines.append(f"  • {scope_prefix}{item.title}")

    remaining = len(group.items) - len(items)
    if remaining > 0:
        lines.append(f"  ...and {remaining} more")

    lines.append("")
    return "\n".join(lines)
