"""Structured file source collector.

Reads change items from a JSON file. This enables:
- Manual release notes supplementation
- CI pipelines that pre-collect data
- Testing without a real git repository
- Migration from other changelog formats

Expected JSON schema:
{
  "changes": [
    {
      "title": "Add user authentication",
      "description": "Optional longer description",
      "category": "feature",
      "scope": "auth",
      "authors": ["alice"],
      "pr_number": 42,
      "issue_numbers": [10, 11],
      "breaking": false,
      "importance": "normal",
      "metadata": {}
    }
  ]
}
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import ChangeItem, ReleaseRange, SourceReference

logger = logging.getLogger("releasepilot.structured")

# Maximum source file size: 50 MB.
_MAX_FILE_SIZE = 50 * 1024 * 1024


class StructuredFileError(Exception):
    """Raised when the structured input file is invalid."""


def _validate_entry(entry: dict, index: int) -> list[str]:
    """Return a list of validation problems for a single entry."""
    problems: list[str] = []
    if not isinstance(entry, dict):
        problems.append(f"Entry {index}: expected an object, got {type(entry).__name__}")
        return problems
    title = entry.get("title")
    if not title or not isinstance(title, str) or not str(title).strip():
        problems.append(f"Entry {index}: missing or empty 'title'")
    cat = entry.get("category")
    if cat is not None and not isinstance(cat, str):
        problems.append(f"Entry {index}: 'category' must be a string, got {type(cat).__name__}")
    imp = entry.get("importance")
    if imp is not None and not isinstance(imp, str):
        problems.append(f"Entry {index}: 'importance' must be a string, got {type(imp).__name__}")
    authors = entry.get("authors")
    if authors is not None and not isinstance(authors, list):
        problems.append(f"Entry {index}: 'authors' must be a list, got {type(authors).__name__}")
    issues = entry.get("issue_numbers")
    if issues is not None and not isinstance(issues, list):
        problems.append(
            f"Entry {index}: 'issue_numbers' must be a list, got {type(issues).__name__}"
        )
    return problems


class StructuredFileCollector:
    """Collects ChangeItems from a JSON file."""

    def __init__(self, file_path: str) -> None:
        self._file_path = Path(file_path)

    def collect(self, release_range: ReleaseRange) -> list[ChangeItem]:
        data = self._load()
        return [self._parse_entry(entry, idx) for idx, entry in enumerate(data)]

    def _load(self) -> list[dict]:
        if not self._file_path.exists():
            raise StructuredFileError(f"File not found: {self._file_path}")

        # Guard against excessively large files.
        try:
            file_size = self._file_path.stat().st_size
        except OSError as exc:
            raise StructuredFileError(f"Cannot read file: {exc}") from exc

        if file_size > _MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            raise StructuredFileError(
                f"Source file is too large ({size_mb:.1f} MB). "
                f"Maximum allowed size is {_MAX_FILE_SIZE // (1024 * 1024)} MB."
            )

        try:
            raw = self._file_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StructuredFileError(f"Invalid JSON: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise StructuredFileError(f"File encoding error (expected UTF-8): {exc}") from exc

        if isinstance(parsed, dict):
            changes = parsed.get("changes", [])
        elif isinstance(parsed, list):
            changes = parsed
        else:
            raise StructuredFileError("Expected a JSON object with 'changes' array or a JSON array")

        if not isinstance(changes, list):
            raise StructuredFileError("'changes' must be a JSON array")

        # Schema validation: check each entry structure.
        all_problems: list[str] = []
        for idx, entry in enumerate(changes):
            all_problems.extend(_validate_entry(entry, idx))
        if all_problems:
            summary = "; ".join(all_problems[:5])
            extra = f" (and {len(all_problems) - 5} more)" if len(all_problems) > 5 else ""
            raise StructuredFileError(f"Schema validation failed: {summary}{extra}")

        return changes

    def _parse_entry(self, entry: dict, index: int) -> ChangeItem:
        title = str(entry.get("title", "")).strip()
        if not title:
            raise StructuredFileError(f"Entry {index} is missing a 'title'")

        item_id = hashlib.sha256(f"structured-{index}-{title}".encode()).hexdigest()[:20]

        category = _parse_category(entry.get("category", "other"))
        importance = _parse_importance(entry.get("importance", "normal"))
        is_breaking = bool(entry.get("breaking", False))
        if is_breaking:
            category = ChangeCategory.BREAKING

        pr_number = entry.get("pr_number")
        issue_numbers = tuple(entry.get("issue_numbers", []))

        return ChangeItem(
            id=item_id,
            title=title,
            description=str(entry.get("description", "")),
            category=category,
            scope=str(entry.get("scope", "")),
            importance=importance,
            is_breaking=is_breaking,
            source=SourceReference(
                pr_number=int(pr_number) if pr_number is not None else None,
                issue_numbers=issue_numbers,
            ),
            authors=tuple(entry.get("authors", [])),
            raw_message=title,
            metadata=dict(entry.get("metadata", {})),
        )


def _parse_category(value: str) -> ChangeCategory:
    try:
        return ChangeCategory(value.lower().strip())
    except ValueError:
        return ChangeCategory.OTHER


def _parse_importance(value: str) -> Importance:
    try:
        return Importance(value.lower().strip())
    except ValueError:
        return Importance.NORMAL
