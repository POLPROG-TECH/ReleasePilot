"""Executive PDF renderer.

Produces a premium, presentation-ready PDF executive brief designed for
management, leadership, and board audiences.

Design principles:
- Strong title block with generous whitespace
- Accent-bar section headings for scannability
- Highlighted executive summary panel
- Visual metrics dashboard (not a plain table)
- Clear visual hierarchy and breathing room throughout
- Risk section with distinct visual treatment
- Minimal, elegant footer
"""

from __future__ import annotations

import io

from releasepilot.audience.executive import ExecutiveBrief
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
_BG_METRICS = "#f1f5f9"
_ACCENT_BAR = "#3b82f6"
_RISK_RED = "#b91c1c"
_RISK_BG = "#fef2f2"
_RISK_BORDER = "#fca5a5"


class ExecutivePdfRenderer:
    """Renders an ExecutiveBrief as a premium PDF document."""

    def render_bytes(
        self, brief: ExecutiveBrief, *, lang: str = "en", accent_color: str = "#FB6400"
    ) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        from releasepilot.rendering.fonts import register_unicode_font

        fn = register_unicode_font()
        fn_b = f"{fn}-Bold" if fn == "UnicodeSans" else "Helvetica-Bold"
        fn_i = fn if fn == "UnicodeSans" else "Helvetica-Oblique"

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
        w = doc.width  # usable content width

        # ── Colour objects ───────────────────────────────────────────────
        c_navy = colors.HexColor(_NAVY)
        c_slate = colors.HexColor(_SLATE)
        c_charcoal = colors.HexColor(_CHARCOAL)
        c_text = colors.HexColor(_TEXT_GRAY)
        c_meta = colors.HexColor(_META_GRAY)
        c_light = colors.HexColor(_LIGHT_GRAY)
        c_border = colors.HexColor(_BORDER)
        c_bg = colors.HexColor(_BG_LIGHT)
        c_bg_metrics = colors.HexColor(_BG_METRICS)
        c_accent = colors.HexColor(accent_color)
        c_risk = colors.HexColor(_RISK_RED)
        c_risk_bg = colors.HexColor(_RISK_BG)

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
            spaceAfter=6,
            textColor=c_charcoal,
        )
        s_summary_body = ParagraphStyle(
            "SummaryBody",
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
        s_bullet = ParagraphStyle(
            "Bullet",
            parent=s_body,
            leftIndent=16,
            bulletIndent=4,
            spaceAfter=4,
        )
        s_numbered = ParagraphStyle(
            "Numbered",
            parent=s_body,
            leftIndent=16,
            spaceAfter=5,
        )
        s_impact_summary = ParagraphStyle(
            "ImpactSummary",
            parent=s_body,
            fontName=fn_i,
            fontSize=10,
            leading=14,
            leftIndent=4,
            textColor=c_text,
            spaceAfter=6,
        )
        s_risk = ParagraphStyle(
            "RiskBullet",
            parent=s_body,
            leftIndent=12,
            spaceAfter=4,
            textColor=c_risk,
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

        meta_parts: list[str] = [brief.localized_date(lang)]
        if rr.version:
            meta_parts.append(f"{get_label('version', lang)} {rr.version}")
        if brief.analysis_period:
            meta_parts.append(
                get_label("analysis_period", lang).format(
                    period=brief.analysis_period,
                ),
            )
        story.append(Paragraph(_esc("  ·  ".join(meta_parts)), s_meta))

        # Thick accent divider after title block
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
        # EXECUTIVE SUMMARY - highlighted panel
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        summary_heading = Paragraph(
            get_label("executive_summary", lang),
            s_heading,
        )
        summary_text = Paragraph(
            _esc(_translate(brief.executive_summary, lang)),
            s_summary_body,
        )
        summary_table = Table(
            [[summary_heading], [Spacer(1, 4)], [summary_text]],
            colWidths=[w - 20],
        )
        summary_table.setStyle(
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
        story.append(summary_table)
        story.append(Spacer(1, 16))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # METRICS DASHBOARD
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        metrics_rows = _build_metrics_rows(brief, lang)
        if len(metrics_rows) > 1:
            story.append(
                _accent_heading(
                    get_label("release_metrics", lang),
                    s_heading,
                    c_accent,
                    w,
                )
            )
            story.append(Spacer(1, 8))

            col_w = [w * 0.60, w * 0.18]
            mt = Table(metrics_rows, colWidths=col_w)
            mt.setStyle(
                TableStyle(
                    [
                        # Header row
                        ("FONTNAME", (0, 0), (-1, 0), fn_b),
                        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
                        ("TEXTCOLOR", (0, 0), (-1, 0), c_slate),
                        ("BACKGROUND", (0, 0), (-1, 0), c_bg_metrics),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.8, c_border),
                        # Data rows
                        ("FONTNAME", (0, 1), (-1, -1), fn),
                        ("FONTSIZE", (0, 1), (-1, -1), 10),
                        ("TEXTCOLOR", (0, 1), (-1, -1), c_charcoal),
                        ("LINEBELOW", (0, 1), (-1, -2), 0.3, colors.HexColor("#f1f5f9")),
                        ("LINEBELOW", (0, -1), (-1, -1), 0.6, c_border),
                        # Values column - bold
                        ("FONTNAME", (1, 1), (1, -1), fn_b),
                        # Spacing
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ("LEFTPADDING", (0, 0), (0, -1), 12),
                        ("RIGHTPADDING", (1, 0), (1, -1), 12),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )
            story.append(mt)
            story.append(Spacer(1, 18))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # KEY ACHIEVEMENTS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if brief.key_achievements:
            story.append(
                _accent_heading(
                    get_label("key_achievements", lang),
                    s_heading,
                    c_accent,
                    w,
                )
            )
            story.append(Spacer(1, 8))
            for i, item in enumerate(brief.key_achievements, 1):
                story.append(
                    Paragraph(
                        f"<b>{i}.</b>  {_esc(item)}",
                        s_numbered,
                    )
                )
            story.append(Spacer(1, 12))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # IMPACT AREAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        for area in brief.impact_areas:
            # Keep heading + summary together to avoid orphaned headings,
            # but let bullet items flow naturally across page breaks.
            header_block: list = [
                _accent_heading(
                    _esc(_translate(area.title, lang)),
                    s_heading,
                    c_accent,
                    w,
                ),
                Spacer(1, 4),
                Paragraph(
                    f"<i>{_esc(_translate(area.summary, lang))}</i>",
                    s_impact_summary,
                ),
                Spacer(1, 2),
            ]
            story.append(KeepTogether(header_block))
            for item in area.items:
                story.append(Paragraph(f"•  {_esc(item)}", s_bullet))
            story.append(Spacer(1, 10))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RISKS - distinct visual treatment
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if brief.risks:
            risk_heading = Paragraph(
                get_label("risks_attention", lang),
                ParagraphStyle(
                    "RiskHead",
                    parent=s_heading,
                    textColor=c_risk,
                ),
            )
            risk_items: list = [risk_heading, Spacer(1, 6)]
            for risk in brief.risks:
                risk_items.append(Paragraph(f"•  {_esc(risk)}", s_risk))

            risk_table = Table(
                [[item] for item in risk_items],
                colWidths=[w - 24],
            )
            risk_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), c_risk_bg),
                        ("LEFTPADDING", (0, 0), (-1, -1), 14),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                        ("TOPPADDING", (0, 0), (0, 0), 10),
                        ("BOTTOMPADDING", (-1, -1), (-1, -1), 10),
                        ("LINEBELOW", (0, 0), (0, 0), 0, c_risk_bg),
                        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                    ]
                )
            )
            # Left accent bar via outer wrapper
            risk_wrapper = Table(
                [[risk_table]],
                colWidths=[w - 20],
            )
            risk_wrapper.setStyle(
                TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (0, 0), 4),
                        ("RIGHTPADDING", (0, 0), (0, 0), 0),
                        ("TOPPADDING", (0, 0), (0, 0), 0),
                        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                        ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
                        ("LINEBEFORE", (0, 0), (0, -1), 3, c_risk),
                    ]
                )
            )
            story.append(risk_wrapper)
            story.append(Spacer(1, 16))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NEXT STEPS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if brief.next_steps:
            story.append(
                _accent_heading(
                    get_label("next_steps", lang),
                    s_heading,
                    c_accent,
                    w,
                )
            )
            story.append(Spacer(1, 6))
            for step in brief.next_steps:
                story.append(
                    Paragraph(
                        f"•  {_esc(_translate(step, lang))}",
                        s_bullet,
                    )
                )
            story.append(Spacer(1, 10))

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
        story.append(Paragraph(footer_html, s_footer))

        doc.build(story)
        return buf.getvalue()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _accent_heading(text: str, style, accent_color, width: float):
    """Section heading with a left accent bar for scannability."""
    from reportlab.platypus import Paragraph, Table, TableStyle

    bar_w = 3.5
    para = Paragraph(text, style)
    t = Table([[para]], colWidths=[width - bar_w - 8])
    t.setStyle(
        TableStyle(
            [
                ("LINEBEFORE", (0, 0), (0, -1), bar_w, accent_color),
                ("LEFTPADDING", (0, 0), (0, 0), 10),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (0, 0), 2),
                ("BOTTOMPADDING", (0, 0), (0, 0), 2),
            ]
        )
    )
    return t


def _build_metrics_rows(
    brief: ExecutiveBrief,
    lang: str = "en",
) -> list[list[str]]:
    """Build translated metrics rows for the dashboard table."""
    from releasepilot.i18n import get_label

    m = brief.metrics
    rows = [[get_label("metric", lang), get_label("value", lang)]]
    rows.append([get_label("total_changes", lang), str(m.get("total_changes", 0))])
    for key, lk in (
        ("features", "new_features"),
        ("improvements", "improvements"),
        ("bugfixes", "issues_resolved"),
        ("performance", "performance_gains"),
        ("security", "security_fixes"),
    ):
        val = m.get(key, 0)
        if val:
            rows.append([get_label(lk, lang), str(val)])
    if m.get("breaking", 0):
        rows.append([get_label("breaking_changes", lang), str(m["breaking"])])
    return rows


def _esc(text: str) -> str:
    """Escape XML special characters for reportlab Paragraph."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
