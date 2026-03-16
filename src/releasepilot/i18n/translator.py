"""Content translator for release note body text.

Uses deep-translator's GoogleTranslator for real-time translation.
Includes placeholder protection to avoid corrupting version numbers,
dates, and other structured values.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("releasepilot.translator")

_PLACEHOLDER_RE = re.compile(
    r"("
    r"v\d+\.\d+(?:\.\d+)?"  # version numbers like v1.2.0
    r"|"
    r"\d{4}-\d{2}-\d{2}"  # ISO dates
    r"|"
    r"\d{2}:\d{2}"  # times
    r"|"
    r"#\d+"  # issue/PR references
    r"|"
    r"`[^`]+`"  # inline code
    r"|"
    r"\*\*[^*]+\*\*"  # bold markdown
    r")"
)


def translate_text(
    text: str,
    target_lang: str,
    source_lang: str = "en",
) -> str:
    """Translate *text* to *target_lang* with placeholder protection.

    Returns the original text unchanged when translation fails or
    ``deep-translator`` is not installed.
    """
    if not text.strip() or target_lang == source_lang:
        return text

    # Protect placeholders
    placeholders: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"__PH{len(placeholders) - 1}__"

    protected = _PLACEHOLDER_RE.sub(_replace, text)

    try:
        from deep_translator import GoogleTranslator  # type: ignore[import-untyped]

        translated = GoogleTranslator(
            source=source_lang,
            target=target_lang,
        ).translate(protected)
    except ImportError:
        logger.debug("deep-translator not installed — skipping translation")
        return text
    except Exception:  # noqa: BLE001
        logger.warning(
            "Translation failed for lang=%s, falling back to original text",
            target_lang,
            exc_info=True,
        )
        return text

    if translated is None:
        return text

    # Restore placeholders
    for i, ph in enumerate(placeholders):
        translated = translated.replace(f"__PH{i}__", ph)

    return translated
