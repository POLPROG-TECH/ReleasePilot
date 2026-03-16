"""Change deduplication.

Detects and reduces duplicate or near-duplicate change items:
1. Exact duplicate detection (same commit hash)
2. PR grouping (multiple commits → one PR entry)
3. Token-overlap similarity (conservative threshold)

Dedup is intentionally conservative to avoid losing real changes.
"""

from __future__ import annotations

from datetime import UTC

from releasepilot.domain.models import ChangeItem


def deduplicate(items: list[ChangeItem]) -> list[ChangeItem]:
    """Remove duplicates and merge related items."""
    items = _remove_exact_duplicates(items)
    items = _merge_by_pr(items)
    items = _remove_near_duplicates(items)
    return items


def _remove_exact_duplicates(items: list[ChangeItem]) -> list[ChangeItem]:
    """Remove items with identical commit hashes."""
    seen_hashes: set[str] = set()
    result: list[ChangeItem] = []

    for item in items:
        key = item.source.commit_hash or item.id
        if key in seen_hashes:
            continue
        seen_hashes.add(key)
        result.append(item)

    return result


def _merge_by_pr(items: list[ChangeItem]) -> list[ChangeItem]:
    """When multiple commits belong to the same PR, keep only the best one."""
    pr_groups: dict[int, list[ChangeItem]] = {}
    non_pr: list[ChangeItem] = []

    for item in items:
        if item.source.pr_number is not None:
            pr_groups.setdefault(item.source.pr_number, []).append(item)
        else:
            non_pr.append(item)

    merged: list[ChangeItem] = []
    for pr_items in pr_groups.values():
        best = _pick_best_item(pr_items)
        merged.append(best)

    return merged + non_pr


def _pick_best_item(items: list[ChangeItem]) -> ChangeItem:
    """Pick the most informative item from a group.

    Prefer: longest description > highest importance > most recent.
    """
    from datetime import datetime

    _epoch = datetime.min.replace(tzinfo=UTC)
    return max(
        items,
        key=lambda i: (
            len(i.description),
            _importance_score(i),
            i.timestamp or _epoch,
        ),
    )


def _remove_near_duplicates(items: list[ChangeItem]) -> list[ChangeItem]:
    """Remove items whose titles are near-identical using token overlap."""
    if len(items) <= 1:
        return items

    result: list[ChangeItem] = []
    seen_signatures: list[set[str]] = []

    for item in items:
        tokens = _tokenize(item.title)
        if _is_near_duplicate(tokens, seen_signatures):
            continue
        seen_signatures.append(tokens)
        result.append(item)

    return result


def _tokenize(text: str) -> set[str]:
    """Extract meaningful tokens from text."""
    words = text.lower().split()
    # Filter out very short words and common noise
    return {w for w in words if len(w) > 2}


def _is_near_duplicate(tokens: set[str], seen: list[set[str]]) -> bool:
    """Check if tokens overlap significantly with any seen signature."""
    if len(tokens) < 3:
        return False

    for existing in seen:
        if len(existing) < 3:
            continue
        overlap = len(tokens & existing)
        smaller = min(len(tokens), len(existing))
        if smaller > 0 and overlap / smaller >= 0.8:
            return True

    return False


def _importance_score(item: ChangeItem) -> int:
    from releasepilot.domain.enums import Importance

    return {
        Importance.HIGH: 3,
        Importance.NORMAL: 2,
        Importance.LOW: 1,
        Importance.NOISE: 0,
    }.get(item.importance, 2)
