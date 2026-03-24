"""Fact extraction for the narrative pipeline.

Transforms ``ChangeItem`` instances from ``ReleaseNotes`` into
``FactItem`` and ``FactGroup`` objects that ground the narrative
in verifiable source data.
"""

from __future__ import annotations

import re

from releasepilot.audience.narrative_models import FactGroup, FactItem
from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
)

# ════════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════════

_COMMIT_PREFIX_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|security|deprecate)"
    r"(\([\w./-]+\))?!?:\s*",
    re.IGNORECASE,
)

_CATEGORY_THEMES: dict[ChangeCategory, str] = {
    ChangeCategory.BREAKING: "Breaking Changes",
    ChangeCategory.SECURITY: "Security",
    ChangeCategory.FEATURE: "New Features",
    ChangeCategory.IMPROVEMENT: "Improvements",
    ChangeCategory.BUGFIX: "Bug Fixes",
    ChangeCategory.PERFORMANCE: "Performance",
    ChangeCategory.DEPRECATION: "Deprecations",
    ChangeCategory.DOCUMENTATION: "Documentation",
    ChangeCategory.INFRASTRUCTURE: "Infrastructure",
    ChangeCategory.REFACTOR: "Refactoring",
    ChangeCategory.OTHER: "Other Changes",
}

# Categories hidden in customer-facing narrative (too technical / internal).
_CUSTOMER_HIDDEN: frozenset[ChangeCategory] = frozenset(
    {
        ChangeCategory.REFACTOR,
        ChangeCategory.INFRASTRUCTURE,
        ChangeCategory.DOCUMENTATION,
        ChangeCategory.OTHER,
    }
)


# ════════════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════════════


def extract_facts(notes: ReleaseNotes) -> list[FactItem]:
    """Extract a flat list of FactItems from ReleaseNotes."""
    highlight_ids = {item.id for item in notes.highlights}
    facts: list[FactItem] = []
    for group in notes.groups:
        for item in group.items:
            facts.append(_item_to_fact(item, is_highlight=item.id in highlight_ids))
    return facts


def extract_fact_groups(
    notes: ReleaseNotes,
    *,
    customer_facing: bool = False,
) -> list[FactGroup]:
    """Extract themed FactGroups from ReleaseNotes.

    Parameters
    ----------
    notes : ReleaseNotes
        The pipeline output containing grouped changes.
    customer_facing : bool
        If True, hides internal/technical categories.
    """
    highlight_ids = {item.id for item in notes.highlights}
    groups: list[FactGroup] = []

    for change_group in notes.groups:
        if customer_facing and change_group.category in _CUSTOMER_HIDDEN:
            continue
        if not change_group.items:
            continue

        facts = tuple(
            _item_to_fact(item, is_highlight=item.id in highlight_ids)
            for item in change_group.items
        )
        theme = _CATEGORY_THEMES.get(change_group.category, "Other Changes")
        summary = _group_summary(change_group)

        groups.append(
            FactGroup(
                theme=theme,
                summary=summary,
                facts=facts,
                category=change_group.category,
            )
        )

    return groups


def collect_all_source_ids(fact_groups: list[FactGroup]) -> frozenset[str]:
    """Collect all ChangeItem IDs referenced across fact groups."""
    ids: set[str] = set()
    for group in fact_groups:
        for fact in group.facts:
            ids.update(fact.source_ids)
    return frozenset(ids)


# ════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════════════════════


def _clean_title(title: str) -> str:
    """Strip conventional-commit prefixes and normalize casing."""
    cleaned = _COMMIT_PREFIX_RE.sub("", title).strip()
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned.rstrip(".") or title


def _item_to_fact(item: ChangeItem, *, is_highlight: bool = False) -> FactItem:
    """Convert a single ChangeItem into a FactItem."""
    text = _clean_title(item.title)
    if item.description:
        first_sentence = item.description.split(".")[0].strip()
        if first_sentence and first_sentence.lower() != text.lower() and len(first_sentence) < 120:
            text = f"{text}: {first_sentence}"

    return FactItem(
        text=text,
        category=item.category,
        source_ids=(item.id,),
        scope=item.scope,
        is_breaking=item.is_breaking,
        is_highlight=is_highlight,
    )


def _group_summary(group: ChangeGroup) -> str:
    """Generate a factual one-line summary for a change group."""
    n = len(group.items)
    cat = group.category
    summaries: dict[ChangeCategory, str] = {
        ChangeCategory.FEATURE: f"{n} new feature{'s' if n != 1 else ''} added",
        ChangeCategory.IMPROVEMENT: f"{n} improvement{'s' if n != 1 else ''} made",
        ChangeCategory.BUGFIX: f"{n} bug{'s' if n != 1 else ''} fixed",
        ChangeCategory.PERFORMANCE: f"{n} performance improvement{'s' if n != 1 else ''} applied",
        ChangeCategory.SECURITY: f"{n} security update{'s' if n != 1 else ''} applied",
        ChangeCategory.BREAKING: f"{n} breaking change{'s' if n != 1 else ''} introduced",
        ChangeCategory.DEPRECATION: f"{n} deprecation{'s' if n != 1 else ''} announced",
        ChangeCategory.DOCUMENTATION: f"{n} documentation update{'s' if n != 1 else ''} made",
        ChangeCategory.INFRASTRUCTURE: f"{n} infrastructure change{'s' if n != 1 else ''} applied",
        ChangeCategory.REFACTOR: f"{n} refactoring{'s' if n != 1 else ''} completed",
        ChangeCategory.OTHER: f"{n} other change{'s' if n != 1 else ''} included",
    }
    return summaries.get(cat, f"{n} change{'s' if n != 1 else ''}")
