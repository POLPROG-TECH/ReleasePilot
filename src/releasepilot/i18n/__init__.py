"""Internationalization support for ReleasePilot.

Provides label translation (static dictionaries for section headings,
UI text) and optional content translation (via deep-translator for
release-note body text).

Supported languages: en, pl, de, fr, es, it, pt, nl, uk, cs
"""

from __future__ import annotations

from releasepilot.i18n.labels import SUPPORTED_LANGUAGES, get_label, get_labels_for
from releasepilot.i18n.translator import translate_text

__all__ = [
    "SUPPORTED_LANGUAGES",
    "get_label",
    "get_labels_for",
    "translate_text",
]
