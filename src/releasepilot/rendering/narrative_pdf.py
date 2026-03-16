"""Narrative PDF renderer.

Produces a polished, prose-style PDF document from a NarrativeBrief.
Unlike the standard PdfRenderer (which produces bullet lists), this renderer
outputs continuous paragraphs suitable for stakeholder communication.

Design mirrors the executive PDF renderer's visual language but adapts
for narrative prose content rather than structured executive sections.
"""

from __future__ import annotations

import io

from releasepilot.audience.narrative import NarrativeBrief
from releasepilot.rendering import REPO_URL


def _translate(text: str, lang: str) -> str:
    """Translate generated text when the target language is not English."""
    if lang == "en" or not text.strip():
        return text
    try:
        from releasepilot.i18n import translate_text

        return translate_text(text, target_lang=lang)
    except Exception:  # noqa: BLE001
        return text


# ── Design tokens ────────────────────────────────────────────────────────────

_NAVY = "#0f172a"
_SLATE = "#334155"
_CHARCOAL = "#1e293b"
_TEXT_GRAY = "#475569"
_META_GRAY = "#64748b"
_LIGHT_GRAY = "#94a3b8"
_BORDER = "#e2e8f0"
_BG_LIGHT = "#f8fafc"
_WARN_AMBER = "#92400e"
_WARN_BG = "#fffbeb"


class NarrativePdfRenderer:
    """Renders a NarrativeBrief as a polished PDF document."""

    def render_bytes(
        self,
        brief: NarrativeBrief,
        *,
        lang: str = "en",
        accent_color: str = "#FB6400",
    ) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        from releasepilot.rendering.fonts import register_unicode_font

        fn = register_unicode_font()
        fn_b = f"{fn}-Bold" if fn == "UnicodeSans" else "Helvetica-Bold"

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            topMargin=28 * mm,
            bottomMargin=22 * mm,
            leftMargin=25 * mm,
            rightMargin=25 * mm,
        )

        styles = getSampleStyleSheet()
        w = doc.width

        # ── Colour objects ───────────────────────────────────────────────
        c_navy = colors.HexColor(_NAVY)
        c_slate = colors.HexColor(_SLATE)
        c_charcoal = colors.HexColor(_CHARCOAL)
        c_meta = colors.HexColor(_META_GRAY)
        c_light = colors.HexColor(_LIGHT_GRAY)
        c_border = colors.HexColor(_BORDER)
        c_bg = colors.HexColor(_BG_LIGHT)
        c_accent = colors.HexColor(accent_color)
        c_warn = colors.HexColor(_WARN_AMBER)
        c_warn_bg = colors.HexColor(_WARN_BG)

        # ── Paragraph styles ─────────────────────────────────────────────
        s_app = ParagraphStyle(
            "AppName",
            parent=styles["Title"],
            fontName=fn_b,
            fontSize=36,
            leading=42,
            spaceAfter=2,
            alignment=1,
            textColor=c_navy,
        )
        s_title = ParagraphStyle(
            "ReportTitle",
            parent=styles["Normal"],
            fontName=fn,
            fontSize=16,
            leading=20,
            spaceAfter=0,
            textColor=c_slate,
        )
        s_meta = ParagraphStyle(
            "Meta",
            parent=styles["Normal"],
            fontName=fn,
            fontSize=9.5,
            leading=13,
            textColor=c_meta,
            spaceAfter=0,
        )
        s_body = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontName=fn,
            fontSize=10.5,
            leading=16,
            spaceAfter=8,
            textColor=c_charcoal,
        )
        s_overview = ParagraphStyle(
            "OverviewBody",
            parent=s_body,
            fontSize=11,
            leading=17,
            spaceAfter=0,
            textColor=c_charcoal,
        )
        s_heading = ParagraphStyle(
            "SectionHead",
            parent=styles["Normal"],
            fontName=fn_b,
            fontSize=12.5,
            leading=16,
            textColor=c_slate,
            spaceAfter=0,
        )
        s_warn = ParagraphStyle(
            "BreakingBody",
            parent=s_body,
            textColor=c_warn,
            spaceAfter=4,
        )
        s_footer = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontName=fn,
            fontSize=7.5,
            leading=10,
            textColor=c_light,
            alignment=1,
        )

        story: list = []
        rr = brief.release_range
        from releasepilot.i18n import get_label

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # TITLE BLOCK
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if rr.app_name:
            story.append(Spacer(1, 4))
            story.append(Paragraph(_esc(rr.app_name), s_app))
            story.append(Spacer(1, 8))

        story.append(Paragraph(_esc(brief.localized_title(lang)), s_title))
        story.append(Spacer(1, 6))

        meta_parts: list[str] = [brief.report_date]
        if rr.version:
            meta_parts.append(f"{get_label('version', lang)} {rr.version}")
        story.append(Paragraph(_esc("  ·  ".join(meta_parts)), s_meta))

        # Thick accent divider
        story.append(Spacer(1, 14))
        story.append(
            HRFlowable(
                width="100%",
                thickness=2.5,
                color=c_accent,
                spaceAfter=0,
                spaceBefore=0,
            )
        )
        story.append(Spacer(1, 18))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # OVERVIEW — highlighted panel
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if brief.mode == "customer-narrative":
            overview_heading_text = get_label("narrative_overview_customer", lang)
        else:
            overview_heading_text = get_label("narrative_overview", lang)

        overview_heading = Paragraph(overview_heading_text, s_heading)
        overview_text = Paragraph(
            _esc(_translate(brief.overview, lang)), s_overview
        )
        overview_table = Table(
            [[overview_heading], [Spacer(1, 4)], [overview_text]],
            colWidths=[w - 20],
        )
        overview_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), c_bg),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                    ("TOPPADDING", (0, 0), (0, 0), 12),
                    ("BOTTOMPADDING", (-1, -1), (-1, -1), 14),
                    ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                ]
            )
        )
        story.append(overview_table)
        story.append(Spacer(1, 16))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BODY PARAGRAPHS — continuous prose
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        for paragraph in brief.body_paragraphs:
            story.append(
                Paragraph(_esc(_translate(paragraph, lang)), s_body)
            )

        if brief.body_paragraphs:
            story.append(Spacer(1, 8))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BREAKING CHANGES — amber warning panel
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if brief.breaking_notice:
            breaking_heading = Paragraph(
                get_label("narrative_breaking", lang),
                ParagraphStyle(
                    "BreakingHead", parent=s_heading, textColor=c_warn
                ),
            )
            breaking_body = Paragraph(
                _esc(_translate(brief.breaking_notice, lang)), s_warn
            )
            breaking_table = Table(
                [[breaking_heading], [Spacer(1, 4)], [breaking_body]],
                colWidths=[w - 24],
            )
            breaking_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), c_warn_bg),
                        ("LEFTPADDING", (0, 0), (-1, -1), 14),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                        ("TOPPADDING", (0, 0), (0, 0), 10),
                        ("BOTTOMPADDING", (-1, -1), (-1, -1), 10),
                        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                    ]
                )
            )
            # Wrap with left accent border
            warn_wrapper = Table(
                [[breaking_table]], colWidths=[w - 20]
            )
            warn_wrapper.setStyle(
                TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (0, 0), 4),
                        ("RIGHTPADDING", (0, 0), (0, 0), 0),
                        ("TOPPADDING", (0, 0), (0, 0), 0),
                        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                        ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
                        ("LINEBEFORE", (0, 0), (0, -1), 3, c_warn),
                    ]
                )
            )
            story.append(warn_wrapper)
            story.append(Spacer(1, 16))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CLOSING
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if brief.closing:
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=c_border,
                    spaceBefore=6,
                    spaceAfter=8,
                )
            )
            closing_style = ParagraphStyle(
                "Closing",
                parent=s_body,
                fontSize=10,
                leading=15,
                textColor=colors.HexColor(_TEXT_GRAY),
            )
            story.append(
                Paragraph(
                    f"<i>{_esc(_translate(brief.closing, lang))}</i>",
                    closing_style,
                )
            )
            story.append(Spacer(1, 8))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FOOTER
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        story.append(Spacer(1, 16))
        story.append(
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=c_border,
                spaceBefore=0,
                spaceAfter=10,
            )
        )
        from datetime import UTC, datetime

        from releasepilot.rendering import AUTHOR, TOOL_NAME

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        footer_tpl = get_label("footer_generated", lang)
        footer_html = footer_tpl.format(
            tool=TOOL_NAME,
            datetime=now,
            author=f'<link href="{REPO_URL}">{AUTHOR}</link>',
        )

        provenance = get_label("narrative_provenance", lang).format(
            fact_count=brief.total_facts,
            source_count=len(brief.source_item_ids),
        )
        story.append(Paragraph(footer_html, s_footer))
        story.append(Paragraph(_esc(provenance), s_footer))

        doc.build(story)
        return buf.getvalue()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _esc(text: str) -> str:
    """Escape XML special characters for reportlab Paragraph."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
