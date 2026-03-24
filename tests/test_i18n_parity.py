"""Test i18n catalog parity between all language catalogs."""

import re

from releasepilot.dashboard.i18n.catalog_en import CATALOG_EN
from releasepilot.dashboard.i18n.catalog_pl import CATALOG_PL


def test_en_pl_key_parity():
    en_keys = set(CATALOG_EN.keys())
    pl_keys = set(CATALOG_PL.keys())
    missing_in_pl = en_keys - pl_keys
    missing_in_en = pl_keys - en_keys
    assert not missing_in_pl, f"Keys missing in PL: {missing_in_pl}"
    assert not missing_in_en, f"Keys missing in EN: {missing_in_en}"


def test_no_empty_values():
    for key, val in CATALOG_EN.items():
        assert val.strip(), f"Empty EN value for key: {key}"
    for key, val in CATALOG_PL.items():
        assert val.strip(), f"Empty PL value for key: {key}"


def test_interpolation_vars_match():
    pattern = re.compile(r"\{(\w+)\}")
    for key in CATALOG_EN:
        en_vars = set(pattern.findall(CATALOG_EN[key]))
        pl_vars = set(pattern.findall(CATALOG_PL.get(key, "")))
        assert en_vars == pl_vars, f"Var mismatch for '{key}': EN={en_vars}, PL={pl_vars}"
