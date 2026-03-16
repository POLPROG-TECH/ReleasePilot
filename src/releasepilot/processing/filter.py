"""Noise filter.

Removes or deprioritizes changes that do not belong in release notes:
- Merge commits (already excluded by git --no-merges, but double-checked)
- WIP / fixup / squash commits
- Trivially short messages
- Pattern-matched noise
- Category-based exclusion

Filtering is configurable via FilterConfig.
"""

from __future__ import annotations

import re
from dataclasses import replace

from releasepilot.config.settings import FilterConfig
from releasepilot.domain.enums import Importance
from releasepilot.domain.models import ChangeItem

# Minimum meaningful title length (in characters)
_MIN_TITLE_LENGTH = 4


def filter_changes(
    items: list[ChangeItem],
    config: FilterConfig,
) -> list[ChangeItem]:
    """Filter out noise and return only meaningful changes."""
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in config.noise_patterns]
    result: list[ChangeItem] = []

    for item in items:
        if _is_noise_by_pattern(item, compiled_patterns):
            continue
        if _is_too_short(item):
            continue
        if _is_excluded_category(item, config):
            continue
        if _is_below_importance(item, config):
            continue
        result.append(item)

    return result


def mark_noise(
    items: list[ChangeItem],
    config: FilterConfig,
) -> list[ChangeItem]:
    """Mark noisy items with NOISE importance instead of removing them."""
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in config.noise_patterns]
    result: list[ChangeItem] = []

    for item in items:
        if _is_noise_by_pattern(item, compiled_patterns) or _is_too_short(item):
            result.append(replace(item, importance=Importance.NOISE))
        else:
            result.append(item)

    return result


def _is_noise_by_pattern(item: ChangeItem, patterns: list[re.Pattern]) -> bool:
    return any(p.search(item.raw_message) for p in patterns)


def _is_too_short(item: ChangeItem) -> bool:
    return len(item.title.strip()) < _MIN_TITLE_LENGTH


def _is_excluded_category(item: ChangeItem, config: FilterConfig) -> bool:
    if config.include_categories is not None:
        return item.category not in config.include_categories
    return item.category in config.exclude_categories


def _is_below_importance(item: ChangeItem, config: FilterConfig) -> bool:
    importance_order = {
        Importance.HIGH: 3,
        Importance.NORMAL: 2,
        Importance.LOW: 1,
        Importance.NOISE: 0,
    }
    min_val = importance_order.get(Importance(config.min_importance), 0)
    item_val = importance_order.get(item.importance, 2)
    return item_val < min_val
