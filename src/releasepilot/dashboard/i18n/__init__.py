"""Dashboard UI i18n package — modular translation catalog for all supported languages.

Usage::

    from releasepilot.dashboard.i18n import get_i18n_catalog

    catalog = get_i18n_catalog()  # {"en": {...}, "pl": {...}, "de": {...}, ...}
"""

from releasepilot.dashboard.i18n.catalog_cs import CATALOG_CS
from releasepilot.dashboard.i18n.catalog_de import CATALOG_DE
from releasepilot.dashboard.i18n.catalog_en import CATALOG_EN
from releasepilot.dashboard.i18n.catalog_es import CATALOG_ES
from releasepilot.dashboard.i18n.catalog_fr import CATALOG_FR
from releasepilot.dashboard.i18n.catalog_it import CATALOG_IT
from releasepilot.dashboard.i18n.catalog_nl import CATALOG_NL
from releasepilot.dashboard.i18n.catalog_pl import CATALOG_PL
from releasepilot.dashboard.i18n.catalog_pt import CATALOG_PT
from releasepilot.dashboard.i18n.catalog_uk import CATALOG_UK

I18N_CATALOG: dict[str, dict[str, str]] = {
    "en": CATALOG_EN,
    "pl": CATALOG_PL,
    "de": CATALOG_DE,
    "fr": CATALOG_FR,
    "es": CATALOG_ES,
    "it": CATALOG_IT,
    "pt": CATALOG_PT,
    "nl": CATALOG_NL,
    "uk": CATALOG_UK,
    "cs": CATALOG_CS,
}


def get_i18n_catalog() -> dict[str, dict[str, str]]:
    """Return the full I18N catalog dictionary (all supported languages)."""
    return I18N_CATALOG
