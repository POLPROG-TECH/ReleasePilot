"""PDF renderer for ReleasePilot.

Produces polished, professional PDF documents suitable for stakeholder
communication, release handoffs, and archival documentation.

Uses reportlab for PDF generation.
"""

from __future__ import annotations

import io

from releasepilot.config.settings import RenderConfig
from releasepilot.domain.models import ChangeItem, ReleaseNotes
from releasepilot.rendering import REPO_URL

# Emoji → text label mapping for clean PDF output
_EMOJI_STRIP = {
    "⚠️": "",
    "🔒": "",
    "✨": "",
    "🔧": "",
    "🐛": "",
    "⚡": "",
    "📦": "",
    "📝": "",
    "🏗️": "",
    "♻️": "",
    "📋": "",
}


def _clean_label(text: str) -> str:
    """Remove emojis from display labels for PDF."""
    for emoji in _EMOJI_STRIP:
        text = text.replace(emoji, "")
    return text.strip()


def _translate_label(text: str, lang: str) -> str:
    """Translate a display label when the target language is not English."""
    if lang == "en" or not text.strip():
        return text
    try:
        from releasepilot.i18n import translate_text

        return translate_text(text, target_lang=lang)
    except Exception:  # noqa: BLE001
        return text


class PdfRenderer:
    """Renders ReleaseNotes as a professional PDF document."""

    def render(self, notes: ReleaseNotes, config: RenderConfig) -> str:
        """PDF is binary — use render_bytes() instead.

        Raises NotImplementedError to prevent silent empty-string returns.
        """
        raise NotImplementedError(
            "PdfRenderer.render() is not supported. Use render_bytes() for PDF output."
        )

    def render_bytes(self, notes: ReleaseNotes, config: RenderConfig) -> bytes:
        """Render release notes to a PDF byte buffer."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        from releasepilot.rendering.fonts import register_unicode_font

        font_name = register_unicode_font()
        font_bold = f"{font_name}-Bold" if font_name == "UnicodeSans" else "Helvetica-Bold"

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            topMargin=25 * mm,
            bottomMargin=20 * mm,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
        )

        styles = getSampleStyleSheet()
        story: list = []

        # Custom styles
        app_name_style = ParagraphStyle(
            "AppName",
            parent=styles["Title"],
            fontName=font_bold,
            fontSize=28,
            spaceAfter=2,
            alignment=1,  # center
            textColor=colors.HexColor("#1a1a2e"),
        )
        title_style = ParagraphStyle(
            "ReleaseTitle",
            parent=styles["Title"],
            fontName=font_bold,
            fontSize=22,
            spaceAfter=4,
            alignment=0,  # left — only app name is centered
            textColor=colors.HexColor("#1a1a2e"),
        )
        subtitle_style = ParagraphStyle(
            "ReleaseSubtitle",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=11,
            textColor=colors.HexColor("#666666"),
            spaceAfter=16,
        )
        section_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontName=font_bold,
            fontSize=14,
            spaceBefore=16,
            spaceAfter=8,
            textColor=colors.HexColor("#16213e"),
            borderWidth=0,
        )
        item_style = ParagraphStyle(
            "BulletItem",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            leftIndent=12,
            bulletIndent=0,
            spaceAfter=3,
        )
        meta_style = ParagraphStyle(
            "MetaInfo",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=8,
            textColor=colors.HexColor("#999999"),
            leftIndent=12,
            spaceAfter=6,
        )
        breaking_item_style = ParagraphStyle(
            "BreakingItem",
            parent=item_style,
            textColor=colors.HexColor("#c0392b"),
        )
        footer_style = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=7,
            textColor=colors.HexColor("#aaaaaa"),
            spaceBefore=20,
            alignment=1,  # center
        )

        rr = notes.release_range
        lang = config.language

        # ── Title block — app name centered on its own, subtitle below ──
        if rr.app_name:
            story.append(Paragraph(_esc(rr.app_name), app_name_style))
            story.append(Spacer(1, 6))
            story.append(Paragraph(_esc(rr.subtitle), title_style))
        else:
            story.append(Paragraph(_esc(rr.display_title), title_style))

        subtitle_parts = []
        if rr.version:
            from releasepilot.i18n import get_label as _label

            subtitle_parts.append(f"{_label('version', lang)} {rr.version}")
        if rr.release_date:
            from releasepilot.i18n import get_label as _label

            released = _label("released_on", lang).format(date=rr.release_date.isoformat())
            subtitle_parts.append(released)
        if notes.metadata.get("pipeline_summary"):
            subtitle_parts.append(notes.metadata["pipeline_summary"])
        if subtitle_parts:
            story.append(Paragraph(" · ".join(subtitle_parts), subtitle_style))

        # Divider line
        accent = colors.HexColor(config.accent_color)
        story.append(Spacer(1, 4))
        divider_data = [[""]]
        divider_table = Table(divider_data, colWidths=[doc.width])
        divider_table.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, 0), 1, accent),
                ]
            )
        )
        story.append(divider_table)
        story.append(Spacer(1, 8))

        # ── Highlights ──
        if notes.highlights:
            from releasepilot.i18n import get_label as _label

            story.append(Paragraph(_label("highlights", lang), section_style))
            for item in notes.highlights:
                story.append(
                    Paragraph(
                        f"• <b>{_esc(item.title)}</b>",
                        item_style,
                    )
                )
                if item.description:
                    story.append(
                        Paragraph(
                            _esc(item.description[:200]),
                            meta_style,
                        )
                    )

        # ── Breaking Changes ──
        if notes.breaking_changes:
            from releasepilot.i18n import get_label as _label

            story.append(Paragraph(_label("breaking_changes", lang), section_style))
            for item in notes.breaking_changes:
                story.append(
                    Paragraph(
                        f"• {_esc(item.title)}",
                        breaking_item_style,
                    )
                )
                if item.description:
                    story.append(
                        Paragraph(
                            _esc(item.description[:300]),
                            meta_style,
                        )
                    )

        # ── Category groups ──
        breaking_ids = {item.id for item in notes.breaking_changes}
        for group in notes.groups:
            if group.category.value == "breaking" and notes.breaking_changes:
                continue

            label = _clean_label(group.display_label)
            label = _translate_label(label, lang)
            story.append(Paragraph(label, section_style))

            for item in group.items:
                if item.id in breaking_ids:
                    continue

                suffix = _item_suffix(item, config)
                text = f"• {_esc(item.title)}{suffix}"
                story.append(Paragraph(text, item_style))

        # ── Footer ──
        from releasepilot.i18n import get_label as _label

        story.append(Spacer(1, 12))
        changes_label = _label("changes_in_release", lang).format(count=notes.total_changes)
        story.append(Paragraph(changes_label, footer_style))
        from datetime import UTC, datetime

        from releasepilot.rendering import AUTHOR, TOOL_NAME

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        footer_tpl = _label("footer_generated", lang)
        footer_html = footer_tpl.format(
            tool=TOOL_NAME, author=f'<link href="{REPO_URL}">{AUTHOR}</link>', datetime=now
        )
        story.append(Paragraph(footer_html, footer_style))

        doc.build(story)
        return buf.getvalue()


def _item_suffix(item: ChangeItem, config: RenderConfig) -> str:
    """Build inline metadata suffix for an item."""
    parts = []
    if config.show_scope and item.scope:
        parts.append(f"<i>[{_esc(item.scope)}]</i>")
    if config.show_authors and item.authors:
        parts.append(f"<i>by {_esc(', '.join(item.authors))}</i>")
    if config.show_commit_hashes and item.source.short_hash:
        parts.append(f"<font size='7' color='#999999'>{item.source.short_hash}</font>")
    if parts:
        return " — " + " ".join(parts)
    return ""


def _esc(text: str) -> str:
    """Escape XML special characters for reportlab Paragraph."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
