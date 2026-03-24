"""Runtime state management for the ReleasePilot web application."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from enum import StrEnum


class AnalysisPhase(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnalysisProgress:
    """Tracks the current state of a generation or dashboard build."""

    phase: AnalysisPhase = AnalysisPhase.IDLE
    stage: str = ""
    detail: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "stage": self.stage,
            "detail": self.detail,
            "error": self.error,
        }


class AppState:
    """Shared mutable state for the web application."""

    def __init__(self, config: dict | None = None) -> None:
        self.config: dict = dict(config) if config else {}
        self.analysis_progress = AnalysisProgress()
        self.analysis_lock = asyncio.Lock()
        self.last_result: dict | None = None
        self.last_dashboard_html: str | None = None
        self._sse_subscribers: list[asyncio.Queue] = []
        # limit max subscribers to prevent memory leak
        self._max_subscribers = 100

    def subscribe(self) -> asyncio.Queue:
        """Create a new SSE subscriber queue."""
        # prune stale subscribers before adding new ones
        self._prune_full_queues()
        if len(self._sse_subscribers) >= self._max_subscribers:
            # Evict oldest subscriber
            self._sse_subscribers.pop(0)
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._sse_subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove an SSE subscriber queue."""
        with contextlib.suppress(ValueError):
            self._sse_subscribers.remove(q)

    def _prune_full_queues(self) -> None:
        """Remove subscriber queues that are full (likely disconnected clients)."""
        self._sse_subscribers = [q for q in self._sse_subscribers if not q.full()]

    async def broadcast(self, event_type: str, data: dict) -> None:
        """Push an event to all SSE subscribers."""
        for q in list(self._sse_subscribers):
            try:
                q.put_nowait({"event": event_type, "data": data})
            except asyncio.QueueFull:
                # remove unresponsive subscribers
                self.unsubscribe(q)
