"""Claim validation for the narrative pipeline.

Verifies that a ``NarrativeBrief`` is grounded in its fact layer:
no marketing language, no unsupported numeric claims, no phantom
category references.
"""

from __future__ import annotations

import re

from releasepilot.audience.narrative_models import (
    FactGroup,
    NarrativeBrief,
    ValidationIssue,
)
from releasepilot.domain.enums import ChangeCategory

# ════════════════════════════════════════════════════════════════════════════
# Forbidden language patterns
# ════════════════════════════════════════════════════════════════════════════

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
    (
        "speculation_expected_to_increase",
        re.compile(r"\bexpected to (?:increase|boost|improve)\b", re.IGNORECASE),
    ),
    ("exaggeration_dramatically", re.compile(r"\bdramatically\b", re.IGNORECASE)),
    ("exaggeration_massive", re.compile(r"\bmassive(?:ly)?\b", re.IGNORECASE)),
    ("exaggeration_incredible", re.compile(r"\bincredib(?:le|ly)\b", re.IGNORECASE)),
]

_NUMBER_RE = re.compile(
    r"\b(\d+)\s+(change|feature|improvement|bug\s*fix|fix|update|optimization|deprecation|refactoring)s?\b",
    re.IGNORECASE,
)


# ════════════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════════════


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
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule="fact_count_mismatch",
                    message=(
                        f"total_facts={brief.total_facts} does not match "
                        f"sum of fact group counts={actual_count}"
                    ),
                )
            )

    return issues


# ════════════════════════════════════════════════════════════════════════════
# Internal checks
# ════════════════════════════════════════════════════════════════════════════


def _check_forbidden_language(text: str) -> list[ValidationIssue]:
    """Detect marketing, speculative, or exaggerated language."""
    issues: list[ValidationIssue] = []
    for rule_name, pattern in _FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        if match:
            issues.append(
                ValidationIssue(
                    severity="error",
                    rule=f"forbidden_language_{rule_name}",
                    message=f"Forbidden language detected: '{match.group()}' violates grounding rules",
                )
            )
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
            issues.append(
                ValidationIssue(
                    severity="warning",
                    rule="numeric_claim_unverified",
                    message=(
                        f"Numeric claim '{claimed_number} {claimed_type}(s)' "
                        f"could not be verified against the fact layer"
                    ),
                )
            )

    return issues


def _check_category_references(
    text: str, fact_groups: tuple[FactGroup, ...]
) -> list[ValidationIssue]:
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
                issues.append(
                    ValidationIssue(
                        severity="error",
                        rule="phantom_category",
                        message=(
                            f"Text references '{kw}' but no {cat.value} "
                            f"category exists in the fact layer"
                        ),
                    )
                )
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
