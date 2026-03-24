"""Executive Markdown renderer.

Produces a polished executive/management report in Markdown format.
Suitable for stakeholder emails, management briefs, and leadership reviews.
"""

from __future__ import annotations

import json
from datetime import date

from releasepilot.audience.executive import ExecutiveBrief


def _translate(text: str, lang: str) -> str:
    """Translate generated text when the target language is not English."""
    if lang == "en" or not text.strip():
        return text
    try:
        from releasepilot.i18n import translate_text

        return translate_text(text, target_lang=lang)
    except Exception:  # noqa: BLE001
        return text


class ExecutiveMarkdownRenderer:
    """Renders an ExecutiveBrief as a polished Markdown report."""

    def render(self, brief: ExecutiveBrief, *, lang: str = "en") -> str:
        parts: list[str] = []
        parts.append(_render_header(brief, lang))
        parts.append(_render_summary(brief, lang))
        parts.append(_render_metrics(brief, lang))

        if brief.key_achievements:
            parts.append(_render_achievements(brief, lang))

        for area in brief.impact_areas:
            parts.append(_render_impact_area(area, lang))

        if brief.risks:
            parts.append(_render_risks(brief, lang))

        if brief.next_steps:
            parts.append(_render_next_steps(brief, lang))

        parts.append(_render_footer(lang))

        return "\n".join(parts)

    def render_json(self, brief: ExecutiveBrief) -> str:
        """Serialize the ExecutiveBrief as structured JSON."""
        return json.dumps(_brief_to_dict(brief), indent=2, ensure_ascii=False)


def _render_header(brief: ExecutiveBrief, lang: str) -> str:
    rr = brief.release_range
    lines: list[str] = []
    if rr.app_name:
        lines.append(f"# {rr.app_name}")
        lines.append(f"\n## {brief.localized_title(lang)}")
    else:
        lines.append(f"# {brief.localized_title(lang)}")
    lines.append("")
    lines.append(f"*{brief.localized_date(lang)}*")
    if rr.version:
        from releasepilot.i18n import get_label

        lines.append(f"*{get_label('version', lang)} {rr.version}*")
    if brief.analysis_period:
        from releasepilot.i18n import get_label

        period_label = get_label("analysis_period", lang).format(
            period=brief.analysis_period,
        )
        lines.append(f"*{period_label}*")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _render_summary(brief: ExecutiveBrief, lang: str) -> str:
    from releasepilot.i18n import get_label

    heading = get_label("executive_summary", lang)
    lines = [f"## {heading}", ""]
    lines.append(_translate(brief.executive_summary, lang))
    lines.append("")
    return "\n".join(lines)


def _render_achievements(brief: ExecutiveBrief, lang: str) -> str:
    from releasepilot.i18n import get_label

    heading = get_label("key_achievements", lang)
    lines = [f"## {heading}", ""]
    for i, item in enumerate(brief.key_achievements, 1):
        lines.append(f"{i}. **{item}**")
    lines.append("")
    return "\n".join(lines)


def _render_impact_area(area, lang: str) -> str:
    lines = [f"## {_translate(area.title, lang)}", ""]
    lines.append(f"*{_translate(area.summary, lang)}*")
    lines.append("")
    for item in area.items:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _render_risks(brief: ExecutiveBrief, lang: str) -> str:
    from releasepilot.i18n import get_label

    heading = get_label("risks_attention", lang)
    lines = [f"## {heading}", ""]
    for risk in brief.risks:
        lines.append(f"- ⚠️ {risk}")
    lines.append("")
    return "\n".join(lines)


def _render_next_steps(brief: ExecutiveBrief, lang: str) -> str:
    from releasepilot.i18n import get_label

    heading = get_label("next_steps", lang)
    lines = [f"## {heading}", ""]
    for step in brief.next_steps:
        lines.append(f"- {_translate(step, lang)}")
    lines.append("")
    return "\n".join(lines)


def _render_metrics(brief: ExecutiveBrief, lang: str) -> str:
    from releasepilot.i18n import get_label

    m = brief.metrics
    heading = get_label("release_metrics", lang)
    lines = [f"## {heading}", ""]
    lines.append(f"| {get_label('metric', lang)} | {get_label('value', lang)} |")
    lines.append("|--------|-------|")
    lines.append(f"| {get_label('total_changes', lang)} | {m.get('total_changes', 0)} |")
    label_map = {
        "features": "new_features",
        "improvements": "improvements",
        "bugfixes": "issues_resolved",
        "performance": "performance_gains",
        "security": "security_fixes",
    }
    for key, label_key in label_map.items():
        val = m.get(key, 0)
        if val:
            lines.append(f"| {get_label(label_key, lang)} | {val} |")
    if m.get("breaking", 0):
        lines.append(f"| {get_label('breaking_changes', lang)} | {m['breaking']} |")
    lines.append("")
    return "\n".join(lines)


def _render_footer(lang: str) -> str:
    from releasepilot.rendering import footer_text

    return f"---\n*{footer_text(include_url=True, lang=lang)}*\n"


def _brief_to_dict(brief: ExecutiveBrief) -> dict:
    """Serialize ExecutiveBrief to a plain dictionary for JSON."""
    rr = brief.release_range
    return {
        "type": "executive_brief",
        "title": brief.report_title,
        "version": rr.version or None,
        "release_date": (rr.release_date or date.today()).isoformat(),
        "executive_summary": brief.executive_summary,
        "key_achievements": list(brief.key_achievements),
        "impact_areas": [
            {
                "title": area.title,
                "summary": area.summary,
                "items": list(area.items),
            }
            for area in brief.impact_areas
        ],
        "risks": list(brief.risks),
        "next_steps": list(brief.next_steps),
        "metrics": brief.metrics,
    }
