"""Change classifier.

Classifies ChangeItems into categories using two strategies:
1. Conventional Commits parsing (primary, when messages follow the convention)
2. Keyword-based fallback (for unstructured commit messages)

Items that already have a non-OTHER category (e.g. from structured input) are
left unchanged.
"""

from __future__ import annotations

import re
from dataclasses import replace

from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import ChangeItem

# Conventional Commits: type(scope): description
_CC_PATTERN = re.compile(
    r"^(?P<type>[a-zA-Z]+)"
    r"(?:\((?P<scope>[^)]*)\))?"
    r"(?P<breaking>!)?"
    r":\s*(?P<description>.+)$",
    re.MULTILINE,
)

_CC_TYPE_MAP: dict[str, ChangeCategory] = {
    "feat": ChangeCategory.FEATURE,
    "fix": ChangeCategory.BUGFIX,
    "docs": ChangeCategory.DOCUMENTATION,
    "style": ChangeCategory.REFACTOR,
    "refactor": ChangeCategory.REFACTOR,
    "perf": ChangeCategory.PERFORMANCE,
    "test": ChangeCategory.INFRASTRUCTURE,
    "build": ChangeCategory.INFRASTRUCTURE,
    "ci": ChangeCategory.INFRASTRUCTURE,
    "chore": ChangeCategory.OTHER,
    "revert": ChangeCategory.BUGFIX,
    "security": ChangeCategory.SECURITY,
    "deprecate": ChangeCategory.DEPRECATION,
}

_KEYWORD_RULES: list[tuple[ChangeCategory, list[str]]] = [
    (ChangeCategory.BREAKING, ["breaking change", "BREAKING"]),
    (ChangeCategory.SECURITY, ["security", "vulnerability", "CVE", "auth fix"]),
    (ChangeCategory.FEATURE, ["add ", "implement", "introduce", "new ", "support "]),
    (ChangeCategory.BUGFIX, ["fix ", "bugfix", "resolve", "patch", "correct ", "hotfix"]),
    (ChangeCategory.PERFORMANCE, ["perf", "optimize", "speed", "faster", "cache"]),
    (ChangeCategory.DEPRECATION, ["deprecat"]),
    (ChangeCategory.DOCUMENTATION, ["doc", "readme", "comment"]),
    (ChangeCategory.INFRASTRUCTURE, ["ci", "build", "deploy", "pipeline", "docker", "workflow"]),
    (ChangeCategory.IMPROVEMENT, ["improve", "enhance", "update", "upgrade", "refine", "polish"]),
    (ChangeCategory.REFACTOR, ["refactor", "restructur", "reorganiz", "clean up", "cleanup"]),
]


def classify(items: list[ChangeItem]) -> list[ChangeItem]:
    """Classify a list of change items, returning new items with updated categories."""
    return [_classify_single(item) for item in items]


def _classify_single(item: ChangeItem) -> ChangeItem:
    # Skip items already classified by source collector
    if item.category != ChangeCategory.OTHER:
        return item

    # Try conventional commit parsing first
    cc_result = _try_conventional_commit(item)
    if cc_result is not None:
        return cc_result

    # Fall back to keyword matching
    return _classify_by_keywords(item)


def _try_conventional_commit(item: ChangeItem) -> ChangeItem | None:
    match = _CC_PATTERN.match(item.raw_message)
    if not match:
        return None

    cc_type = match.group("type").lower()
    scope = match.group("scope") or ""
    is_breaking = match.group("breaking") == "!"
    description = match.group("description").strip()

    # Also check for BREAKING CHANGE footer
    if not is_breaking and "BREAKING CHANGE" in item.raw_message:
        is_breaking = True

    category = _CC_TYPE_MAP.get(cc_type, ChangeCategory.OTHER)
    if is_breaking:
        category = ChangeCategory.BREAKING

    importance = Importance.HIGH if is_breaking else Importance.NORMAL

    return replace(
        item,
        title=description,
        category=category,
        scope=scope or item.scope,
        is_breaking=is_breaking,
        importance=importance,
    )


def _classify_by_keywords(item: ChangeItem) -> ChangeItem:
    text = item.raw_message.lower()

    for category, keywords in _KEYWORD_RULES:
        if any(kw.lower() in text for kw in keywords):
            is_breaking = category == ChangeCategory.BREAKING or item.is_breaking
            importance = Importance.HIGH if is_breaking else item.importance
            return replace(
                item,
                category=category,
                is_breaking=is_breaking,
                importance=importance,
            )

    return item
