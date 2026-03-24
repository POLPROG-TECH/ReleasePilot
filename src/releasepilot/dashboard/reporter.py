"""HTML reporter for the ReleasePilot dashboard."""

from __future__ import annotations

from releasepilot.dashboard.renderer import DashboardRenderer
from releasepilot.dashboard.schema import DashboardData
from releasepilot.dashboard.view_models import build_dashboard_vm


class HtmlReporter:
    """Renders a self-contained HTML dashboard from DashboardData."""

    def __init__(self) -> None:
        self._renderer = DashboardRenderer()

    def render(self, data: DashboardData) -> str:
        """Produce a complete HTML document string."""
        vm = build_dashboard_vm(data)
        return self._renderer.render(vm)
