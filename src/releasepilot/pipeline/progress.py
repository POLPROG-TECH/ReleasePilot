"""Pipeline progress reporting.

Provides a callback-based progress system for reporting pipeline stages
to the UI layer. The pipeline itself remains UI-agnostic — callers supply
a callback to receive progress updates.
"""

from __future__ import annotations

from typing import Protocol


class ProgressCallback(Protocol):
    """Callable that receives pipeline progress updates."""

    def __call__(self, stage: str, detail: str = "", current: int = 0, total: int = 0) -> None: ...


# Stage constants used by the orchestrator
STAGE_BUILD_RANGE = "Building release range"
STAGE_COLLECTING = "Collecting commits"
STAGE_CLASSIFYING = "Classifying changes"
STAGE_FILTERING = "Filtering noise"
STAGE_DEDUPLICATING = "Deduplicating entries"
STAGE_GROUPING = "Grouping release items"
STAGE_COMPOSING = "Preparing statistics"
STAGE_RENDERING = "Rendering document"
STAGE_TRANSLATING = "Translating output"
STAGE_EXPORTING = "Exporting file"


def noop_progress(stage: str, detail: str = "", current: int = 0, total: int = 0) -> None:
    """No-op progress callback for non-interactive usage."""
