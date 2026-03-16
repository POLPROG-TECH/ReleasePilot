"""Narrative plaintext renderer.

Produces clean, terminal-friendly prose output from a NarrativeBrief.
Unlike the standard PlaintextRenderer (which uses bullet lists), this
renderer outputs continuous paragraphs.
"""

from __future__ import annotations

from releasepilot.audience.narrative import NarrativeBrief


class NarrativePlaintextRenderer:
    """Renders a NarrativeBrief as plain text prose."""

    def render(self, brief: NarrativeBrief) -> str:
        if not brief.overview:
            return "No notable changes in this release.\n"

        parts: list[str] = []
        parts.append(_render_header(brief))
        parts.append(brief.overview)
        parts.append("")

        for paragraph in brief.body_paragraphs:
            parts.append(paragraph)
            parts.append("")

        if brief.breaking_notice:
            parts.append("BREAKING CHANGES:")
            parts.append(brief.breaking_notice)
            parts.append("")

        if brief.closing:
            parts.append(brief.closing)
            parts.append("")

        parts.append(f"({brief.total_facts} changes from {len(brief.source_item_ids)} source items)")

        return "\n".join(parts)


def _render_header(brief: NarrativeBrief) -> str:
    title = brief.report_title
    rr = brief.release_range
    if rr.app_name:
        title = f"{rr.app_name} — {title}"
    sep = "=" * len(title)
    lines = [title, sep]

    if rr.release_date:
        lines.append(f"Date: {rr.release_date.isoformat()}")

    lines.append("")
    return "\n".join(lines)
