from __future__ import annotations

import json
import re
from typing import Any

from releasepilot.shared.logging import get_logger

logger = get_logger("web.dashboard")


# Thin header bar injected into the self-contained dashboard HTML.
# Template uses {nonce} placeholder filled at serve-time.
HEADER_BAR_TEMPLATE = """\
<style nonce="{nonce}">\
:root{{--portal-bar-h:30px}}\
#rp-portal-bar{{position:sticky;top:0;z-index:9999;\
background:linear-gradient(135deg,#1e293b,#334155);\
color:#f8fafc;padding:6px 16px;\
font-family:system-ui,sans-serif;font-size:13px;\
display:flex;align-items:center;justify-content:space-between;\
box-shadow:0 1px 3px rgba(0,0,0,.3)}}\
#rp-portal-bar .rp-brand{{font-weight:600}}\
#rp-portal-bar .rp-back{{color:#94a3b8;text-decoration:none;font-size:12px}}\
</style>\
<div id="rp-portal-bar">
  <span class="rp-brand" data-i18n="ui.nav.portal">🚀 ReleasePilot</span>
  <a href="/" class="rp-back" data-i18n="ui.nav.back">⬅ Back to Portal</a>
</div>
"""


def sse_format(event: str, data: dict | str) -> str:
    """Format a server-sent event."""
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def build_settings_from_config(config: dict) -> Any:
    """Build a ``Settings`` object from a config dict."""
    from datetime import date

    from releasepilot.config.settings import RenderConfig, Settings
    from releasepilot.domain.enums import Audience, OutputFormat

    audience_str = config.get("audience", "changelog")
    format_str = config.get("output_format", config.get("format", "markdown"))

    try:
        audience = Audience(audience_str)
    except ValueError:
        audience = Audience.CHANGELOG

    try:
        output_format = OutputFormat(format_str)
    except ValueError:
        output_format = OutputFormat.MARKDOWN

    lang = config.get("language", "en")

    since_date = config.get("since_date", "")
    from_ref = config.get("from_ref", "")

    if not since_date and not from_ref:
        today = date.today()
        month_ago = today.month - 1 or 12
        year_ago = today.year if today.month > 1 else today.year - 1
        try:
            since_dt = date(year_ago, month_ago, today.day)
        except ValueError:
            import calendar

            last_day = calendar.monthrange(year_ago, month_ago)[1]
            since_dt = date(year_ago, month_ago, last_day)
        since_date = since_dt.isoformat()
        config["since_date"] = since_date

    multi_sources_raw = config.get("multi_repo_sources", ())
    multi_sources = tuple(dict(s) for s in multi_sources_raw) if multi_sources_raw else ()

    return Settings(
        repo_path=config.get("repo_path", "."),
        from_ref=from_ref,
        to_ref=config.get("to_ref", "HEAD"),
        branch=config.get("branch", ""),
        since_date=since_date,
        audience=audience,
        output_format=output_format,
        version=config.get("version", ""),
        title=config.get("title", ""),
        app_name=config.get("app_name", ""),
        language=lang,
        render=RenderConfig(language=lang),
        gitlab_url=config.get("gitlab_url", ""),
        gitlab_token=config.get("gitlab_token", ""),
        gitlab_project=config.get("gitlab_project", ""),
        gitlab_ssl_verify=config.get("gitlab_ssl_verify", True),
        github_token=config.get("github_token", ""),
        github_owner=config.get("github_owner", ""),
        github_repo=config.get("github_repo", ""),
        github_url=config.get("github_url", "https://api.github.com"),
        github_ssl_verify=config.get("github_ssl_verify", True),
        multi_repo_sources=multi_sources,
    )


def generate_dashboard_full(config: dict) -> tuple[str, dict]:
    """Run the pipeline and return ``(html_string, data_dict)``."""
    from releasepilot.dashboard.reporter import HtmlReporter
    from releasepilot.dashboard.use_case import DashboardUseCase
    from releasepilot.dashboard.view_models import serialize_data

    settings = build_settings_from_config(config)
    if settings.is_github_source:
        logger.info(
            "Generating dashboard from GitHub: %s/%s",
            settings.github_owner,
            settings.github_repo,
        )
    elif settings.is_gitlab_source:
        logger.info("Generating dashboard from GitLab: %s", settings.gitlab_project)
    elif settings.is_multi_repo:
        src_labels = [
            s.get("app_label", s.get("url", s.get("path", "?")))
            for s in settings.multi_repo_sources
        ]
        logger.info(
            "Generating dashboard from %d multi-repo sources: %s",
            len(settings.multi_repo_sources),
            ", ".join(src_labels),
        )
    else:
        logger.info("Generating dashboard from local repo: %s", settings.repo_path)

    data = DashboardUseCase().execute(settings)
    html = HtmlReporter().render(data)
    return html, serialize_data(data)


def generate_dashboard_html(config: dict) -> str:
    """Run the dashboard pipeline (synchronous) and return HTML string."""
    html, _ = generate_dashboard_full(config)
    return html


def inject_header_bar(html: str, nonce: str) -> str:
    """Insert the portal header bar after <body> in the dashboard HTML."""
    marker = "<body>"
    idx = html.lower().find(marker)
    if idx == -1:
        return html
    insert_at = idx + len(marker)
    bar = HEADER_BAR_TEMPLATE.format(nonce=nonce)
    return html[:insert_at] + "\n" + bar + html[insert_at:]


def inject_csp_nonce(html: str, nonce: str) -> str:
    """Add a CSP nonce attribute to all inline <style> and <script> tags."""
    html = re.sub(r"<style(?=[\s>])", f'<style nonce="{nonce}"', html)
    html = re.sub(r"<script(?=[\s>])", f'<script nonce="{nonce}"', html)
    return html
