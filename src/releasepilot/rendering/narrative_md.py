"""Narrative Markdown renderer.

Produces a polished, prose-style Markdown document from a NarrativeBrief.
Unlike the standard MarkdownRenderer (which produces bullet lists), this
renderer outputs continuous paragraphs suitable for stakeholder communication.
"""

from __future__ import annotations

import json
from datetime import date

from releasepilot.audience.narrative import NarrativeBrief


class NarrativeMarkdownRenderer:
    """Renders a NarrativeBrief as continuous Markdown prose."""

    def render(self, brief: NarrativeBrief, *, lang: str = "en") -> str:
        parts: list[str] = []
        parts.append(_render_header(brief, lang))
        parts.append(_render_overview(brief, lang))

        for paragraph in brief.body_paragraphs:
            parts.append(_render_paragraph(paragraph, lang))

        if brief.breaking_notice:
            parts.append(_render_breaking(brief, lang))

        if brief.closing:
            parts.append(_render_closing(brief, lang))

        parts.append(_render_footer(brief, lang))

        return "\n".join(parts)

    def render_json(self, brief: NarrativeBrief) -> str:
        """Serialize the NarrativeBrief as structured JSON."""
        return json.dumps(_brief_to_dict(brief), indent=2, ensure_ascii=False)


def _render_header(brief: NarrativeBrief, lang: str) -> str:
    rr = brief.release_range
    lines: list[str] = []

    if rr.app_name:
        lines.append(f"# {rr.app_name}")
        lines.append(f"\n## {brief.localized_title(lang)}")
    else:
        lines.append(f"# {brief.localized_title(lang)}")

    lines.append("")
    lines.append(f"*{brief.report_date}*")
    if rr.version:
        from releasepilot.i18n import get_label
        lines.append(f"*{get_label('version', lang)} {rr.version}*")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _render_overview(brief: NarrativeBrief, lang: str) -> str:
    from releasepilot.i18n import get_label

    if brief.mode == "customer-narrative":
        heading = get_label("narrative_overview_customer", lang)
    else:
        heading = get_label("narrative_overview", lang)

    lines = [f"## {heading}", ""]
    lines.append(_translate(brief.overview, lang))
    lines.append("")
    return "\n".join(lines)


def _render_paragraph(paragraph: str, lang: str) -> str:
    return _translate(paragraph, lang) + "\n"


def _render_breaking(brief: NarrativeBrief, lang: str) -> str:
    from releasepilot.i18n import get_label

    heading = get_label("narrative_breaking", lang)
    lines = [f"## ⚠️ {heading}", ""]
    lines.append(_translate(brief.breaking_notice, lang))
    lines.append("")
    return "\n".join(lines)


def _render_closing(brief: NarrativeBrief, lang: str) -> str:
    lines = ["---", ""]
    lines.append(f"*{_translate(brief.closing, lang)}*")
    lines.append("")
    return "\n".join(lines)


def _render_footer(brief: NarrativeBrief, lang: str) -> str:
    from releasepilot.rendering import footer_text

    lines: list[str] = []
    lines.append(f"*{footer_text(include_url=True, lang=lang)}*")

    # Provenance note — how many source facts back this narrative
    from releasepilot.i18n import get_label
    provenance = get_label("narrative_provenance", lang).format(
        fact_count=brief.total_facts,
        source_count=len(brief.source_item_ids),
    )
    lines.append(f"\n*{provenance}*")
    lines.append("")
    return "\n".join(lines)


def _translate(text: str, lang: str) -> str:
    """Translate text when the target language is not English."""
    if lang == "en" or not text.strip():
        return text
    try:
        from releasepilot.i18n import translate_text
        return translate_text(text, target_lang=lang)
    except Exception:  # noqa: BLE001
        return text


def _brief_to_dict(brief: NarrativeBrief) -> dict:
    """Serialize NarrativeBrief to a plain dictionary for JSON."""
    rr = brief.release_range
    return {
        "type": "narrative_brief",
        "mode": brief.mode,
        "title": brief.report_title,
        "version": rr.version or None,
        "release_date": (rr.release_date or date.today()).isoformat(),
        "overview": brief.overview,
        "body_paragraphs": list(brief.body_paragraphs),
        "breaking_notice": brief.breaking_notice or None,
        "closing": brief.closing or None,
        "total_facts": brief.total_facts,
        "source_item_count": len(brief.source_item_ids),
        "fact_groups": [
            {
                "theme": g.theme,
                "summary": g.summary,
                "category": g.category.value,
                "facts": [
                    {
                        "text": f.text,
                        "category": f.category.value,
                        "source_ids": list(f.source_ids),
                        "scope": f.scope or None,
                        "is_breaking": f.is_breaking,
                        "is_highlight": f.is_highlight,
                    }
                    for f in g.facts
                ],
            }
            for g in brief.fact_groups
        ],
    }
