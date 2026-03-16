"""Fact-grounded narrative pipeline for ReleasePilot.

Transforms ``ReleaseNotes`` into a ``NarrativeBrief`` — a continuous prose
summary of release changes suitable for stakeholder communication,
client-facing updates, and management briefs.

This module mirrors the executive pipeline (``audience/executive.py``)
in structure: composition logic and domain models live here; renderers
live in ``rendering/narrative_md.py`` and ``rendering/narrative_plain.py``.

Architecture
============
::

    Standard pipeline:  ReleaseNotes → MarkdownRenderer (bullets)
    Executive pipeline: ReleaseNotes → ExecutiveBrief  → ExecutiveRenderer
    Narrative pipeline: ReleaseNotes → NarrativeBrief  → NarrativeRenderer (prose)
                            ↑ shared boundary

Truthfulness guarantee
======================
Every sentence is derived from an inspectable fact layer, not from
unconstrained text generation.  The ``validate_narrative`` function
can verify that no unsupported claims have been introduced.

Stages
======
1. **Fact extraction** — ``ChangeItem`` → ``FactItem`` / ``FactGroup``
2. **Narrative composition** — ``FactGroup`` list → ``NarrativeBrief``
3. **Claim validation** — checks the brief against grounding rules
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
)

# ════════════════════════════════════════════════════════════════════════════
# Models
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FactItem:
    """A single verified fact extracted from source change data.

    Every fact is traceable: ``source_ids`` links back to the original
    ChangeItem identifiers so the narrative can be audited.
    """

    text: str
    category: ChangeCategory
    source_ids: tuple[str, ...] = ()
    scope: str = ""
    is_breaking: bool = False
    is_highlight: bool = False


@dataclass(frozen=True)
class FactGroup:
    """A thematic group of related facts.

    Groups are used to structure the narrative into coherent paragraphs.
    Each group has a human-readable theme label and a summary sentence.
    """

    theme: str
    summary: str
    facts: tuple[FactItem, ...]
    category: ChangeCategory = ChangeCategory.OTHER

    @property
    def count(self) -> int:
        return len(self.facts)


@dataclass(frozen=True)
class NarrativeBrief:
    """A fact-grounded narrative summary of a release.

    This is the central output model of the narrative pipeline.
    Every field is derived from verified facts, not from free-form generation.
    """

    release_range: ReleaseRange
    overview: str
    body_paragraphs: tuple[str, ...] = ()
    breaking_notice: str = ""
    closing: str = ""
    fact_groups: tuple[FactGroup, ...] = ()
    total_facts: int = 0
    source_item_ids: frozenset[str] = field(default_factory=frozenset)
    mode: str = "narrative"

    @property
    def report_title(self) -> str:
        rr = self.release_range
        label = "Product Update" if self.mode == "customer-narrative" else "Release Summary"
        if rr.version:
            return f"{label} — v{rr.version}"
        if rr.title:
            return f"{label} — {rr.title}"
        return label

    def localized_title(self, lang: str = "en") -> str:
        """Return report title with the label portion translated."""
        from releasepilot.i18n import get_label

        if self.mode == "customer-narrative":
            label = get_label("customer_narrative_title", lang)
        else:
            label = get_label("narrative_title", lang)
        rr = self.release_range
        if rr.version:
            return f"{label} — v{rr.version}"
        if rr.title:
            return f"{label} — {rr.title}"
        return label

    @property
    def report_date(self) -> str:
        d = self.release_range.release_date or date.today()
        return d.strftime("%B %d, %Y")

    @property
    def full_text(self) -> str:
        """The complete narrative as a single string (for validation)."""
        parts = [self.overview]
        parts.extend(self.body_paragraphs)
        if self.breaking_notice:
            parts.append(self.breaking_notice)
        if self.closing:
            parts.append(self.closing)
        return "\n\n".join(parts)


# ════════════════════════════════════════════════════════════════════════════
# Fact extraction
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
_CUSTOMER_HIDDEN: frozenset[ChangeCategory] = frozenset({
    ChangeCategory.REFACTOR,
    ChangeCategory.INFRASTRUCTURE,
    ChangeCategory.DOCUMENTATION,
    ChangeCategory.OTHER,
})


def _clean_title(title: str) -> str:
    """Strip conventional-commit prefixes and normalize casing."""
    cleaned = _COMMIT_PREFIX_RE.sub("", title).strip()
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned.rstrip(".") or title


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

        groups.append(FactGroup(
            theme=theme,
            summary=summary,
            facts=facts,
            category=change_group.category,
        ))

    return groups


def collect_all_source_ids(fact_groups: list[FactGroup]) -> frozenset[str]:
    """Collect all ChangeItem IDs referenced across fact groups."""
    ids: set[str] = set()
    for group in fact_groups:
        for fact in group.facts:
            ids.update(fact.source_ids)
    return frozenset(ids)


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


# ════════════════════════════════════════════════════════════════════════════
# Narrative composition
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
                additional_details = [_fact_to_sentence(f, customer_facing) for f in non_highlights[:2]]
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
            f"{n - 5} additional breaking change{'s are' if n - 5 != 1 else ' is'} "
            f"also included."
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


# ════════════════════════════════════════════════════════════════════════════
# Claim validation
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding."""

    severity: str  # "error" or "warning"
    rule: str  # machine-readable rule name
    message: str  # human-readable description


_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("superlative_best", re.compile(r"\bbest[- ]in[- ]class\b", re.IGNORECASE)),
    ("superlative_revolutionary", re.compile(r"\brevolutionary\b", re.IGNORECASE)),
    ("superlative_groundbreaking", re.compile(r"\bgroundbreaking\b", re.IGNORECASE)),
    ("marketing_game_changer", re.compile(r"\bgame[- ]?changer\b", re.IGNORECASE)),
    ("marketing_cutting_edge", re.compile(r"\bcutting[- ]?edge\b", re.IGNORECASE)),
    ("marketing_world_class", re.compile(r"\bworld[- ]?class\b", re.IGNORECASE)),
    ("marketing_industry_leading", re.compile(r"\bindustry[- ]?leading\b", re.IGNORECASE)),
    ("marketing_state_of_art", re.compile(r"\bstate[- ]of[- ]the[- ]art\b", re.IGNORECASE)),
    ("marketing_seamless", re.compile(r"\bseamless(?:ly)?\b", re.IGNORECASE)),
    ("marketing_unparalleled", re.compile(r"\bunparalleled\b", re.IGNORECASE)),
    ("speculation_will_transform", re.compile(r"\bwill transform\b", re.IGNORECASE)),
    ("speculation_will_revolutionize", re.compile(r"\bwill revolutionize\b", re.IGNORECASE)),
    ("speculation_expected_to_increase", re.compile(r"\bexpected to (?:increase|boost|improve)\b", re.IGNORECASE)),
    ("exaggeration_dramatically", re.compile(r"\bdramatically\b", re.IGNORECASE)),
    ("exaggeration_massive", re.compile(r"\bmassive(?:ly)?\b", re.IGNORECASE)),
    ("exaggeration_incredible", re.compile(r"\bincredib(?:le|ly)\b", re.IGNORECASE)),
]

_NUMBER_RE = re.compile(
    r"\b(\d+)\s+(change|feature|improvement|bug\s*fix|fix|update|optimization|deprecation|refactoring)s?\b",
    re.IGNORECASE,
)


def validate_narrative(brief: NarrativeBrief) -> list[ValidationIssue]:
    """Validate a NarrativeBrief against its fact layer.

    Returns an empty list if the narrative is fully grounded.
    """
    issues: list[ValidationIssue] = []
    full_text = brief.full_text

    issues.extend(_check_forbidden_language(full_text))
    issues.extend(_check_numeric_claims(full_text, brief.fact_groups))
    issues.extend(_check_category_references(full_text, brief.fact_groups))

    if brief.total_facts > 0:
        actual_count = sum(g.count for g in brief.fact_groups)
        if brief.total_facts != actual_count:
            issues.append(ValidationIssue(
                severity="error",
                rule="fact_count_mismatch",
                message=(
                    f"total_facts={brief.total_facts} does not match "
                    f"sum of fact group counts={actual_count}"
                ),
            ))

    return issues


def _check_forbidden_language(text: str) -> list[ValidationIssue]:
    """Detect marketing, speculative, or exaggerated language."""
    issues: list[ValidationIssue] = []
    for rule_name, pattern in _FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        if match:
            issues.append(ValidationIssue(
                severity="error",
                rule=f"forbidden_language_{rule_name}",
                message=f"Forbidden language detected: '{match.group()}' violates grounding rules",
            ))
    return issues


def _check_numeric_claims(text: str, fact_groups: tuple[FactGroup, ...]) -> list[ValidationIssue]:
    """Verify numeric claims in the narrative match the fact layer."""
    issues: list[ValidationIssue] = []

    category_counts: dict[str, int] = {}
    total_count = 0
    for group in fact_groups:
        total_count += group.count
        for label in _category_text_forms(group.category):
            category_counts[label] = group.count

    for match in _NUMBER_RE.finditer(text):
        claimed_number = int(match.group(1))
        claimed_type = match.group(2).lower().strip()

        if claimed_type == "change" and claimed_number == total_count:
            continue

        matched = False
        for label, expected in category_counts.items():
            if claimed_type in label or label in claimed_type:  # noqa: SIM102
                if claimed_number == expected:
                    matched = True
                    break

        if not matched and claimed_number != total_count:
            issues.append(ValidationIssue(
                severity="warning",
                rule="numeric_claim_unverified",
                message=(
                    f"Numeric claim '{claimed_number} {claimed_type}(s)' "
                    f"could not be verified against the fact layer"
                ),
            ))

    return issues


def _check_category_references(text: str, fact_groups: tuple[FactGroup, ...]) -> list[ValidationIssue]:
    """Check that category references in text correspond to actual fact groups."""
    issues: list[ValidationIssue] = []
    present_categories = {g.category for g in fact_groups}
    text_lower = text.lower()

    category_keywords: dict[ChangeCategory, list[str]] = {
        ChangeCategory.SECURITY: ["security update", "security change", "security-related"],
        ChangeCategory.DEPRECATION: ["deprecation", "deprecated", "will be retired"],
    }

    for cat, keywords in category_keywords.items():
        for kw in keywords:
            if kw in text_lower and cat not in present_categories:
                issues.append(ValidationIssue(
                    severity="error",
                    rule="phantom_category",
                    message=(
                        f"Text references '{kw}' but no {cat.value} "
                        f"category exists in the fact layer"
                    ),
                ))
                break

    return issues


def _category_text_forms(cat: ChangeCategory) -> list[str]:
    """Return text forms that a category might appear as in narrative."""
    forms: dict[ChangeCategory, list[str]] = {
        ChangeCategory.FEATURE: ["feature", "addition"],
        ChangeCategory.IMPROVEMENT: ["improvement", "enhancement"],
        ChangeCategory.BUGFIX: ["bug fix", "fix", "bug", "issue"],
        ChangeCategory.PERFORMANCE: ["optimization", "performance"],
        ChangeCategory.SECURITY: ["security", "update"],
        ChangeCategory.BREAKING: ["breaking change", "change"],
        ChangeCategory.DEPRECATION: ["deprecation"],
        ChangeCategory.DOCUMENTATION: ["documentation"],
        ChangeCategory.INFRASTRUCTURE: ["infrastructure"],
        ChangeCategory.REFACTOR: ["refactoring"],
    }
    return forms.get(cat, ["change"])
