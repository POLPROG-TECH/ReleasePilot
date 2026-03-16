"""JSON renderer.

Produces structured JSON export of release notes for:
- API consumption
- CI/CD integration
- Further processing by other tools
"""

from __future__ import annotations

import json

from releasepilot.config.settings import RenderConfig
from releasepilot.domain.models import ChangeGroup, ChangeItem, ReleaseNotes


class JsonRenderer:
    """Renders ReleaseNotes as structured JSON."""

    def render(self, notes: ReleaseNotes, config: RenderConfig) -> str:
        data = _serialize_notes(notes)
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _serialize_notes(notes: ReleaseNotes) -> dict:
    return {
        "release": {
            "version": notes.release_range.version,
            "title": notes.release_range.display_title,
            "date": (
                notes.release_range.release_date.isoformat()
                if notes.release_range.release_date
                else None
            ),
            "from_ref": notes.release_range.from_ref,
            "to_ref": notes.release_range.to_ref,
        },
        "total_changes": notes.total_changes,
        "highlights": [_serialize_item(i) for i in notes.highlights],
        "breaking_changes": [_serialize_item(i) for i in notes.breaking_changes],
        "groups": [_serialize_group(g) for g in notes.groups],
        "metadata": notes.metadata,
    }


def _serialize_group(group: ChangeGroup) -> dict:
    return {
        "category": group.category.value,
        "label": group.display_label,
        "count": len(group.items),
        "items": [_serialize_item(i) for i in group.items],
    }


def _serialize_item(item: ChangeItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "category": item.category.value,
        "scope": item.scope,
        "importance": item.importance.value,
        "is_breaking": item.is_breaking,
        "authors": list(item.authors),
        "source": {
            "commit_hash": item.source.commit_hash,
            "pr_number": item.source.pr_number,
            "issue_numbers": list(item.source.issue_numbers),
        },
        "timestamp": item.timestamp.isoformat() if item.timestamp else None,
    }
