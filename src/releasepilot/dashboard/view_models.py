"""View-model builder — converts ``DashboardData`` into a plain dict for Jinja2 templates.

The single entry point is :func:`build_dashboard_vm`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from releasepilot.dashboard.i18n import get_i18n_catalog
from releasepilot.dashboard.renderer import DashboardRenderer
from releasepilot.dashboard.schema import DashboardData


def build_dashboard_vm(data: DashboardData) -> dict[str, Any]:
    """Build the complete template context (``vm``) for the dashboard.

    The returned dict is passed to ``DashboardRenderer.render(vm=...)`` and
    is available in every Jinja2 partial as ``{{ vm.… }}``.
    """
    renderer = DashboardRenderer()
    data_dict = _serialize(data)
    i18n_catalog = get_i18n_catalog()

    return {
        "dashboard_data_json": renderer.safe_json_for_html(data_dict),
        "i18n_catalog_json": renderer.safe_json_for_html(i18n_catalog),
        "generated_at": _html_escape(
            data.generated_at or datetime.now().isoformat(timespec="seconds"),
        ),
        "generated_year": _html_escape(
            (data.generated_at or datetime.now().isoformat())[:4],
        ),
        "app_version": _html_escape(_get_version()),
        "repo_path": _html_escape(data.repo_path),
    }


def serialize_data(data: DashboardData) -> dict[str, Any]:
    """Convert *data* to a JSON-serializable dict (public API)."""
    return _serialize(data)


def _serialize(data: DashboardData) -> dict[str, Any]:
    """Convert DashboardData to a JSON-serializable dict."""
    d = asdict(data)
    d["is_empty"] = data.is_empty
    d["total_breaking"] = data.total_breaking
    d["total_highlights"] = data.total_highlights
    d["categories_used"] = data.categories_used
    d["total_authors"] = data.total_authors
    d["scopes_used"] = data.scopes_used
    return d


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("releasepilot")
    except Exception:  # noqa: BLE001
        return "1.1.0"
