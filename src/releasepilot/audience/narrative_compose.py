"""Narrative composition for the narrative pipeline.

Assembles ``FactGroup`` lists into a ``NarrativeBrief`` - continuous
prose paragraphs suitable for stakeholder communication.
"""

from __future__ import annotations

from releasepilot.audience.narrative_facts import (
    collect_all_source_ids,
    extract_fact_groups,
)
from releasepilot.audience.narrative_models import (
    FactGroup,
    FactItem,
    NarrativeBrief,
)
from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import ReleaseNotes, ReleaseRange

# ════════════════════════════════════════════════════════════════════════════
# Main entry point
# ════════════════════════════════════════════════════════════════════════════


def compose_narrative(
    notes: ReleaseNotes,
    *,
    customer_facing: bool = False,
) -> NarrativeBrief:
    """Compose a grounded narrative brief from release notes.

    This is the main entry point.  It extracts facts, composes prose
    paragraphs, and assembles a ``NarrativeBrief`` ready for rendering.
    """
    mode = "customer-narrative" if customer_facing else "narrative"
    fact_groups = extract_fact_groups(notes, customer_facing=customer_facing)

    if not fact_groups:
        return _empty_narrative(notes.release_range, mode)

    overview = _compose_overview(notes.release_range, fact_groups, customer_facing)
    body_paragraphs = _compose_body(fact_groups, customer_facing)
    breaking_notice = _compose_breaking_notice(fact_groups)
    closing = _compose_closing(notes.release_range, fact_groups, customer_facing)

    total_facts = sum(g.count for g in fact_groups)
    source_ids = collect_all_source_ids(fact_groups)

    return NarrativeBrief(
        release_range=notes.release_range,
        overview=overview,
        body_paragraphs=tuple(body_paragraphs),
        breaking_notice=breaking_notice,
        closing=closing,
        fact_groups=tuple(fact_groups),
        total_facts=total_facts,
        source_item_ids=source_ids,
        mode=mode,
    )


# ── Overview paragraph ──────────────────────────────────────────────────


def _compose_overview(
    rr: ReleaseRange,
    fact_groups: list[FactGroup],
    customer_facing: bool,
) -> str:
    """Generate the opening paragraph summarizing the release scope."""
    total_facts = sum(g.count for g in fact_groups)
    group_count = len(fact_groups)

    subject = rr.app_name or "This release"
    version_part = f" version {rr.version}" if rr.version else ""

    area_descriptions = _describe_areas(fact_groups, customer_facing)

    if customer_facing:
        opening = (
            f"{subject}{version_part} includes {total_facts} "
            f"change{'s' if total_facts != 1 else ''} "
            f"across {group_count} area{'s' if group_count != 1 else ''}."
        )
    else:
        opening = (
            f"{subject}{version_part} contains {total_facts} "
            f"change{'s' if total_facts != 1 else ''} "
            f"spanning {group_count} area{'s' if group_count != 1 else ''}."
        )

    if area_descriptions:
        opening += f" {area_descriptions}"

    return opening


def _describe_areas(fact_groups: list[FactGroup], customer_facing: bool) -> str:
    """Build a natural-language list of the areas covered."""
    if not fact_groups:
        return ""

    area_parts: list[str] = []
    for group in fact_groups:
        n = group.count
        theme = group.theme.lower()
        area_parts.append(f"{n} {theme}")

    prefix = "This update covers" if customer_facing else "The changes include"

    return f"{prefix} {_join_natural(area_parts)}."


# ── Body paragraphs ─────────────────────────────────────────────────────


def _compose_body(
    fact_groups: list[FactGroup],
    customer_facing: bool,
) -> list[str]:
    """Generate one paragraph per fact group."""
    paragraphs: list[str] = []
    for group in fact_groups:
        if group.category == ChangeCategory.BREAKING:
            continue
        paragraph = _group_to_paragraph(group, customer_facing)
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs


def _group_to_paragraph(group: FactGroup, customer_facing: bool) -> str:
    """Convert a single FactGroup into a readable paragraph."""
    n = group.count
    facts = group.facts
    if n == 0:
        return ""

    sentences: list[str] = []

    if customer_facing:  # noqa: SIM108
        opener = _customer_opener(group)
    else:
        opener = _technical_opener(group)
    sentences.append(opener)

    highlights = [f for f in facts if f.is_highlight]
    non_highlights = [f for f in facts if not f.is_highlight]

    if n <= 4:
        for fact in facts:
            sentences.append(_fact_to_sentence(fact, customer_facing))
    else:
        for fact in highlights[:3]:
            sentences.append(_fact_to_sentence(fact, customer_facing))
        mentioned = min(len(highlights), 3)
        remaining = n - mentioned
        if remaining > 0:
            if non_highlights:
                additional_details = [
                    _fact_to_sentence(f, customer_facing) for f in non_highlights[:2]
                ]
                sentences.extend(additional_details)
                rest = remaining - min(len(non_highlights), 2)
                if rest > 0:
                    sentences.append(
                        f"Additionally, {rest} more "
                        f"change{'s were' if rest != 1 else ' was'} made in this area."
                    )
            else:
                remaining_hl = n - mentioned
                if remaining_hl > 0:
                    sentences.append(
                        f"{remaining_hl} additional "
                        f"change{'s were' if remaining_hl != 1 else ' was'} "
                        f"also included."
                    )

    return " ".join(sentences)


def _customer_opener(group: FactGroup) -> str:
    """Opening sentence for customer-facing narrative."""
    openers: dict[ChangeCategory, str] = {
        ChangeCategory.FEATURE: f"This release introduces {group.count} new feature{'s' if group.count != 1 else ''}.",
        ChangeCategory.IMPROVEMENT: f"{group.count} improvement{'s have' if group.count != 1 else ' has'} been made to existing functionality.",
        ChangeCategory.BUGFIX: f"{group.count} issue{'s have' if group.count != 1 else ' has'} been resolved in this update.",
        ChangeCategory.PERFORMANCE: f"Performance has been improved with {group.count} optimization{'s' if group.count != 1 else ''}.",
        ChangeCategory.SECURITY: f"{group.count} security update{'s have' if group.count != 1 else ' has'} been applied.",
        ChangeCategory.DEPRECATION: f"{group.count} feature{'s' if group.count != 1 else ''} will be retired in a future release.",
    }
    return openers.get(
        group.category,
        f"{group.count} change{'s were' if group.count != 1 else ' was'} made in {group.theme.lower()}.",
    )


def _technical_opener(group: FactGroup) -> str:
    """Opening sentence for technical/stakeholder narrative."""
    openers: dict[ChangeCategory, str] = {
        ChangeCategory.FEATURE: f"In the area of new features, {group.count} addition{'s were' if group.count != 1 else ' was'} made.",
        ChangeCategory.IMPROVEMENT: f"The release includes {group.count} improvement{'s' if group.count != 1 else ''} to existing functionality.",
        ChangeCategory.BUGFIX: f"{group.count} bug fix{'es were' if group.count != 1 else ' was'} applied.",
        ChangeCategory.PERFORMANCE: f"{group.count} performance optimization{'s were' if group.count != 1 else ' was'} implemented.",
        ChangeCategory.SECURITY: f"{group.count} security-related change{'s were' if group.count != 1 else ' was'} made.",
        ChangeCategory.DEPRECATION: f"{group.count} deprecation{'s were' if group.count != 1 else ' was'} announced.",
        ChangeCategory.DOCUMENTATION: f"{group.count} documentation update{'s were' if group.count != 1 else ' was'} made.",
        ChangeCategory.INFRASTRUCTURE: f"Infrastructure changes include {group.count} update{'s' if group.count != 1 else ''}.",
        ChangeCategory.REFACTOR: f"{group.count} refactoring change{'s were' if group.count != 1 else ' was'} completed.",
    }
    return openers.get(
        group.category,
        f"{group.count} change{'s were' if group.count != 1 else ' was'} made in {group.theme.lower()}.",
    )


def _fact_to_sentence(fact: FactItem, customer_facing: bool) -> str:
    """Convert a single fact into a readable sentence."""
    text = fact.text
    if not text.endswith("."):
        text = text + "."
    if not customer_facing and fact.scope:  # noqa: SIM102
        if f"({fact.scope})" not in text and fact.scope.lower() not in text.lower():
            text = text.rstrip(".") + f" (in {fact.scope})."
    return text


# ── Breaking changes notice ─────────────────────────────────────────────


def _compose_breaking_notice(fact_groups: list[FactGroup]) -> str:
    """Generate a paragraph about breaking changes, if any."""
    breaking_groups = [g for g in fact_groups if g.category == ChangeCategory.BREAKING]
    if not breaking_groups:
        return ""

    breaking_facts: list[FactItem] = []
    for g in breaking_groups:
        breaking_facts.extend(g.facts)

    if not breaking_facts:
        return ""

    n = len(breaking_facts)
    sentences = [
        f"This release includes {n} breaking "
        f"change{'s' if n != 1 else ''} that may require attention."
    ]
    for fact in breaking_facts[:5]:
        text = fact.text
        if not text.endswith("."):
            text += "."
        sentences.append(text)

    if n > 5:
        sentences.append(
            f"{n - 5} additional breaking change{'s are' if n - 5 != 1 else ' is'} also included."
        )

    return " ".join(sentences)


# ── Closing paragraph ───────────────────────────────────────────────────


def _compose_closing(
    rr: ReleaseRange,
    fact_groups: list[FactGroup],
    customer_facing: bool,
) -> str:
    """Generate a brief closing sentence."""
    total = sum(g.count for g in fact_groups)
    n_areas = len(fact_groups)

    if customer_facing:
        if rr.version:
            return f"Version {rr.version} reflects {total} change{'s' if total != 1 else ''} to the product."
        return f"This update includes {total} change{'s' if total != 1 else ''} in total."
    else:
        if rr.version:
            return (
                f"In total, version {rr.version} comprises {total} "
                f"change{'s' if total != 1 else ''} across "
                f"{n_areas} area{'s' if n_areas != 1 else ''}."
            )
        return (
            f"This release comprises {total} "
            f"change{'s' if total != 1 else ''} across "
            f"{n_areas} area{'s' if n_areas != 1 else ''}."
        )


def _empty_narrative(rr: ReleaseRange, mode: str) -> NarrativeBrief:
    """Return a minimal narrative for an empty release."""
    subject = rr.app_name or "This release"
    version_part = f" version {rr.version}" if rr.version else ""
    return NarrativeBrief(
        release_range=rr,
        overview=f"{subject}{version_part} contains no notable changes.",
        body_paragraphs=(),
        mode=mode,
    )


def _join_natural(items: list[str]) -> str:
    """Join items with commas and 'and': 'a, b, and c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
