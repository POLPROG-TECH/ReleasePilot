"""Jinja2 dashboard renderer for ReleasePilot.

Follows the same pattern as ``releaseboard.presentation.renderer``:
a thin wrapper around a Jinja2 ``Environment`` with a ``FileSystemLoader``
pointed at the ``templates/`` directory next to this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class DashboardRenderer:
    """Render the ReleasePilot dashboard from Jinja2 templates."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(default_for_string=True, default=True),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, vm: dict[str, Any]) -> str:
        """Render ``dashboard.html.j2`` with the given view-model dict."""
        template = self._env.get_template("dashboard.html.j2")
        return template.render(vm=vm)

    @staticmethod
    def safe_json_for_html(data: Any) -> str:
        """Serialize *data* to JSON safe for embedding inside ``<script>`` tags."""
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        raw = raw.replace("</", r"<\/")
        raw = raw.replace("\u2028", "\\u2028")
        raw = raw.replace("\u2029", "\\u2029")
        return raw
