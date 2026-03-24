"""Markdown renderer.

Produces polished markdown release notes suitable for:
- GitHub Releases
- CHANGELOG.md
- Documentation sites
"""

from __future__ import annotations

from releasepilot.config.settings import RenderConfig
from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import ChangeGroup, ChangeItem, ReleaseNotes


def _translate(text: str, lang: str) -> str:
    """Translate *text* when the target language is not English.

    Returns the original text if translation fails or is unavailable.
    """
    if lang == "en" or not text.strip():
        return text
    from releasepilot.i18n import translate_text

    return translate_text(text, target_lang=lang)


class MarkdownRenderer:
    """Renders ReleaseNotes as polished Markdown."""

    def render(self, notes: ReleaseNotes, config: RenderConfig) -> str:
        if notes.is_empty:
            return _empty_release(notes, config)

        lang = config.language

        parts: list[str] = []
        parts.append(_render_header(notes, lang))

        # Stats block — provides transparency about the analysis
        stats_block = _render_stats_block(notes, lang)
        if stats_block:
            parts.append(stats_block)

        if notes.highlights:
            parts.append(_render_highlights(notes, config, lang))

        if notes.breaking_changes:
            parts.append(_render_breaking_changes(notes, config, lang))

        for group in notes.groups:
            # Skip BREAKING group when already rendered as dedicated section
            if notes.breaking_changes and group.category == ChangeCategory.BREAKING:
                continue
            rendered = _render_group(group, config, lang)
            if rendered:
                parts.append(rendered)

        parts.append(_render_footer(notes, lang))

        return "\n".join(parts)


def _empty_release(notes: ReleaseNotes, config: RenderConfig) -> str:
    from releasepilot.i18n import get_label

    lang = config.language
    title = notes.release_range.display_title
    no_changes = get_label("no_notable_changes", lang)
    return f"# {title}\n\n{no_changes}\n"


def _render_header(notes: ReleaseNotes, lang: str) -> str:
    from releasepilot.i18n import get_label

    rr = notes.release_range
    lines: list[str] = []

    # App name alone on the top line, subtitle below
    if rr.app_name:
        lines.append(f"# {rr.app_name}")
        lines.append(f"\n## {rr.subtitle}")
    else:
        lines.append(f"# {rr.display_title}")

    if rr.release_date:
        released_on = get_label("released_on", lang).format(date=rr.release_date.isoformat())
        lines.append(f"\n> {released_on}")

    if notes.metadata.get("summary"):
        lines.append(f"\n{notes.metadata['summary']}")

    lines.append("")
    return "\n".join(lines)


def _render_highlights(notes: ReleaseNotes, config: RenderConfig, lang: str) -> str:
    from releasepilot.i18n import get_label

    heading = get_label("highlights", lang)
    lines = [f"## 🔥 {heading}", ""]
    for item in notes.highlights:
        lines.append(f"- **{item.title}**{_item_suffix(item, config)}")
    lines.append("")
    return "\n".join(lines)


def _render_breaking_changes(notes: ReleaseNotes, config: RenderConfig, lang: str) -> str:
    from releasepilot.i18n import get_label

    heading = get_label("breaking_changes", lang)
    lines = [f"## ⚠️ {heading}", ""]
    for item in notes.breaking_changes:
        lines.append(f"- **{item.title}**{_item_suffix(item, config)}")
        if item.description:
            desc = _translate(item.description.strip(), lang)
            for desc_line in desc.splitlines():
                lines.append(f"  {desc_line}")
    lines.append("")
    return "\n".join(lines)


def _render_group(group: ChangeGroup, config: RenderConfig, lang: str = "en") -> str:
    if not group.items:
        return ""

    items = group.items
    if config.max_items_per_group > 0:
        items = items[: config.max_items_per_group]

    label = _translate(group.display_label, lang)
    lines = [f"## {label}", ""]
    for item in items:
        lines.append(f"- {item.title}{_item_suffix(item, config)}")

    remaining = len(group.items) - len(items)
    if remaining > 0:
        lines.append(f"- *...and {remaining} more*")

    lines.append("")
    return "\n".join(lines)


def _render_stats_block(notes: ReleaseNotes, lang: str) -> str:
    """Render an optional statistics summary block near the top."""
    from releasepilot.i18n import get_label

    md = notes.metadata
    if not md.get("raw_count"):
        return ""

    heading = get_label("release_metrics", lang)
    lines = [f"### 📊 {heading}", ""]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| {get_label('total_changes', lang)} | {notes.total_changes} |")
    if md.get("raw_count") and md.get("raw_count") != str(notes.total_changes):
        lines.append(f"| {get_label('raw_changes', lang)} | {md['raw_count']} |")
    if md.get("filtered_out") and md["filtered_out"] != "0":
        lines.append(f"| {get_label('filtered_out', lang)} | {md['filtered_out']} |")
    if md.get("deduplicated") and md["deduplicated"] != "0":
        lines.append(f"| {get_label('deduplicated', lang)} | {md['deduplicated']} |")
    if md.get("final_count"):
        lines.append(f"| {get_label('final_changes', lang)} | {md['final_count']} |")
    if md.get("contributors"):
        lines.append(f"| {get_label('contributors', lang)} | {md['contributors']} |")
    if md.get("first_commit_date"):
        lines.append(f"| {get_label('first_commit', lang)} | {md['first_commit_date']} |")
    if md.get("last_commit_date"):
        lines.append(f"| {get_label('last_commit', lang)} | {md['last_commit_date']} |")
    if md.get("effective_branch"):
        lines.append(f"| {get_label('branch', lang)} | {md['effective_branch']} |")
    if md.get("components"):
        lines.append(f"| {get_label('components', lang)} | {md['components']} |")
    lines.append("")
    return "\n".join(lines)


def _render_footer(notes: ReleaseNotes, lang: str) -> str:
    from releasepilot.i18n import get_label
    from releasepilot.rendering import footer_text

    changes_label = get_label("changes_in_release", lang).format(count=notes.total_changes)
    lines = [f"---\n*{changes_label}*"]

    # Pipeline transparency: show how items were reduced
    pipeline_summary = notes.metadata.get("pipeline_summary")
    if pipeline_summary:
        lines.append(f"\n*Pipeline: {pipeline_summary}*")

    lines.append(f"\n*{footer_text(include_url=True, lang=lang)}*\n")
    return "\n".join(lines)


def _item_suffix(item: ChangeItem, config: RenderConfig) -> str:
    """Build the inline suffix (scope, author, hash, PR link)."""
    parts: list[str] = []

    if config.show_scope and item.scope:
        parts.append(f"`{item.scope}`")

    if config.show_authors and item.authors:
        parts.append(f"by {', '.join(item.authors)}")

    if config.show_commit_hashes and item.source.short_hash:
        parts.append(f"`{item.source.short_hash}`")

    if config.show_pr_links and item.source.pr_number is not None:
        parts.append(f"(#{item.source.pr_number})")

    if not parts:
        return ""
    return " — " + " ".join(parts)
