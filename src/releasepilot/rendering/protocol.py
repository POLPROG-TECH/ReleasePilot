"""Renderer protocol.

All output renderers implement this protocol.
"""

from __future__ import annotations

from typing import Protocol

from releasepilot.config.settings import RenderConfig
from releasepilot.domain.models import ReleaseNotes


class Renderer(Protocol):
    """Renders ReleaseNotes into a specific output format."""

    def render(self, notes: ReleaseNotes, config: RenderConfig) -> str:
        """Render release notes to a string in the target format."""
        ...
