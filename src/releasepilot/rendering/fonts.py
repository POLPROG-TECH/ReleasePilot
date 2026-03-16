"""Unicode font registration for PDF renderers.

Registers a Unicode-capable TrueType font so that Polish, Czech, Ukrainian,
and other non-ASCII diacritics render correctly in PDF output.

The module tries the following fonts in order:
1. DejaVu Sans (commonly bundled on Linux)
2. Arial Unicode MS (available on macOS and Windows)
3. Falls back to Helvetica (Latin-1 only) when no Unicode font is found.
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

# Sentinel for "already tried to register"
_registered_font: str | None = None
_init_done = False

# Common paths for Unicode-capable TTF files (normal, bold)
_CANDIDATES: list[tuple[str, str | None]] = [
    # Linux — DejaVu with bold variant
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    # macOS — Arial Unicode (single weight only)
    ("/Library/Fonts/Arial Unicode.ttf", None),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", None),
    # Windows
    ("C:\\Windows\\Fonts\\arialuni.ttf", None),
    ("C:\\Windows\\Fonts\\DejaVuSans.ttf", "C:\\Windows\\Fonts\\DejaVuSans-Bold.ttf"),
]


def _find_ttf() -> tuple[str, str | None] | None:
    """Return (normal_path, bold_path_or_None) for the first available font."""
    for normal, bold in _CANDIDATES:
        if os.path.isfile(normal):
            bold_ok = bold and os.path.isfile(bold)
            return (normal, bold if bold_ok else None)
    return None


def register_unicode_font() -> str:
    """Register a Unicode font and return its family name.

    Returns ``"UnicodeSans"`` when a TrueType font was registered, or
    ``"Helvetica"`` as a fallback.
    """
    global _registered_font, _init_done  # noqa: PLW0603

    if _init_done:
        return _registered_font or "Helvetica"

    _init_done = True

    result = _find_ttf()
    if result is None:
        _log.debug("No Unicode TTF font found — using Helvetica fallback")
        return "Helvetica"

    normal_path, bold_path = result

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont("UnicodeSans", normal_path))

        # Register bold — use dedicated bold file if available, else reuse normal
        bold_src = bold_path or normal_path
        pdfmetrics.registerFont(TTFont("UnicodeSans-Bold", bold_src))

        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily(
            "UnicodeSans",
            normal="UnicodeSans",
            bold="UnicodeSans-Bold",
        )

        _registered_font = "UnicodeSans"
        _log.debug("Registered Unicode font from %s", normal_path)
        return "UnicodeSans"
    except Exception:  # noqa: BLE001
        _log.debug("Failed to register Unicode font", exc_info=True)
        return "Helvetica"
