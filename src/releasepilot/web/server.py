"""ReleasePilot FastAPI web application.

Single ``create_app()`` factory with all routes defined as inner functions,
following the ReleaseBoard architectural pattern.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import re
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from releasepilot import __version__
from releasepilot.shared.logging import get_logger
from releasepilot.web.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from releasepilot.web.state import (
    AnalysisPhase,
    AnalysisProgress,
    AppState,
    WizardStep,
)

logger = get_logger("web.server")

# ── Constants ──────────────────────────────────────────────────────────────

# Maximum request body size (1 MB)
MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024

# Pipeline execution timeout (5 minutes)
GENERATION_TIMEOUT_SECONDS = 300

# Rate limiting: max requests per window per client
_RATE_LIMIT_MAX = 30
_RATE_LIMIT_WINDOW = 60  # seconds

# Repo path validation — reject shell metacharacters and traversal
_REPO_PATH_UNSAFE_RE = re.compile(r"[;|&`$(){}\[\]!#~]")

# 1×1 transparent PNG for favicon
_FAVICON_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNl7BcQAAAABJRU5ErkJggg=="
)

# Thin header bar injected into the self-contained dashboard HTML.
# Template uses {nonce} placeholder filled at serve-time.
_HEADER_BAR_TEMPLATE = """\
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


def _validate_repo_path(path: str) -> str | None:
    """Validate repo_path for safety. Returns error message or None if valid."""
    if not path or path == ".":
        return None
    if _REPO_PATH_UNSAFE_RE.search(path):
        return f"repo_path contains unsafe characters: '{path}'"
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        return f"repo_path does not exist or is not a directory: '{path}'"
    return None


def _check_git_available() -> bool:
    """Return True if the git binary is available on PATH."""
    return shutil.which("git") is not None


def _sse_format(event: str, data: dict | str) -> str:
    """Format a server-sent event."""
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _build_settings_from_config(config: dict) -> Any:
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

    # Default to 1 month ago when no range is specified
    if not since_date and not from_ref:
        today = date.today()
        month_ago = today.month - 1 or 12
        year_ago = today.year if today.month > 1 else today.year - 1
        try:
            since_dt = date(year_ago, month_ago, today.day)
        except ValueError:
            # Handle e.g. March 31 -> Feb 28
            import calendar

            last_day = calendar.monthrange(year_ago, month_ago)[1]
            since_dt = date(year_ago, month_ago, last_day)
        since_date = since_dt.isoformat()
        config["since_date"] = since_date

    # Multi-repo sources
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
        # Remote source settings
        gitlab_url=config.get("gitlab_url", ""),
        gitlab_token=config.get("gitlab_token", ""),
        gitlab_project=config.get("gitlab_project", ""),
        gitlab_ssl_verify=config.get("gitlab_ssl_verify", True),
        github_token=config.get("github_token", ""),
        github_owner=config.get("github_owner", ""),
        github_repo=config.get("github_repo", ""),
        github_url=config.get("github_url", "https://api.github.com"),
        github_ssl_verify=config.get("github_ssl_verify", True),
        # Multi-repo sources
        multi_repo_sources=multi_sources,
    )


def _generate_dashboard_html(config: dict) -> str:
    """Run the dashboard pipeline (synchronous) and return HTML string."""
    html, _ = _generate_dashboard_full(config)
    return html


def _generate_dashboard_full(config: dict) -> tuple[str, dict]:
    """Run the pipeline and return ``(html_string, data_dict)``."""
    from releasepilot.dashboard.reporter import HtmlReporter
    from releasepilot.dashboard.use_case import DashboardUseCase
    from releasepilot.dashboard.view_models import serialize_data

    settings = _build_settings_from_config(config)
    # Log which source is being used for debugging
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


def _inject_header_bar(html: str, nonce: str) -> str:
    """Insert the portal header bar after <body> in the dashboard HTML."""
    marker = "<body>"
    idx = html.lower().find(marker)
    if idx == -1:
        return html
    insert_at = idx + len(marker)
    bar = _HEADER_BAR_TEMPLATE.format(nonce=nonce)
    return html[:insert_at] + "\n" + bar + html[insert_at:]


def _inject_csp_nonce(html: str, nonce: str) -> str:
    """Add a CSP nonce attribute to all inline <style> and <script> tags."""
    html = re.sub(r"<style(?=[\s>])", f'<style nonce="{nonce}"', html)
    html = re.sub(r"<script(?=[\s>])", f'<script nonce="{nonce}"', html)
    return html


def create_app(config: dict | None = None, *, root_path: str = "") -> FastAPI:
    """Application factory — returns a fully configured FastAPI instance."""

    state = AppState(config)
    start_time = time.monotonic()

    # API key auth — read from env or config
    api_key = os.environ.get(
        "RELEASEPILOT_API_KEY",
        (state.config or {}).get("api_key", ""),
    )

    # Rate limiter state — simple in-memory per-IP tracker
    _rate_buckets: dict[str, list[float]] = {}

    # Track background generation task
    _background_tasks: list[asyncio.Task] = []

    # Track auto-generate health
    _startup_generation_failed = False

    # ── Lifespan ────────────────────────────────────────────────────────

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        nonlocal _startup_generation_failed

        # Check git availability at startup
        if not _check_git_available():
            logger.warning("git binary not found on PATH — pipeline operations will fail")

        logger.info("ReleasePilot v%s starting", __version__)
        if state.config.get("repo_path") and state.config["repo_path"] != ".":
            task = asyncio.create_task(_auto_generate_dashboard())
            _background_tasks.append(task)
        yield
        # Graceful shutdown — cancel pending tasks
        for task in _background_tasks:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(task, timeout=5.0)
        _background_tasks.clear()
        logger.info("ReleasePilot shutting down")

    async def _auto_generate_dashboard() -> None:
        """Background task: auto-generate dashboard on startup."""
        nonlocal _startup_generation_failed
        try:
            html = await asyncio.to_thread(_generate_dashboard_html, state.config)
            state.last_dashboard_html = html
            logger.info("Auto-generated dashboard on startup")
        except Exception:
            _startup_generation_failed = True
            logger.exception("Failed to auto-generate dashboard on startup")

    # ── Auth helper ────────────────────────────────────────

    def _check_auth(request: Request) -> JSONResponse | None:
        """Return a 401 response if auth is enabled and the key is wrong."""
        if not api_key:
            return None  # auth disabled
        header = request.headers.get("Authorization", "")
        if header == f"Bearer {api_key}":
            return None
        return JSONResponse(
            {"ok": False, "error": "Unauthorized"},
            status_code=401,
        )

    # ── Rate limiter helper ────────────────────────────────

    def _check_rate_limit(request: Request) -> JSONResponse | None:
        """Return a 429 response if the client exceeded the rate limit."""
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = _rate_buckets.setdefault(client_ip, [])
        # Prune old entries
        cutoff = now - _RATE_LIMIT_WINDOW
        _rate_buckets[client_ip] = bucket = [t for t in bucket if t > cutoff]
        if len(bucket) >= _RATE_LIMIT_MAX:
            return JSONResponse(
                {"ok": False, "error": "Rate limit exceeded"},
                status_code=429,
            )
        bucket.append(now)
        return None

    # ── Body size helper ────────────────────────────────────

    async def _read_json_body(request: Request) -> tuple[dict | None, JSONResponse | None]:
        """Read and parse JSON body with size limit. Returns (body, error_response)."""
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            return None, JSONResponse(
                {"ok": False, "error": "Request body too large"},
                status_code=413,
            )
        try:
            raw = await request.body()
        except Exception:
            return {}, None
        if len(raw) > MAX_REQUEST_BODY_BYTES:
            return None, JSONResponse(
                {"ok": False, "error": "Request body too large"},
                status_code=413,
            )
        if not raw:
            return {}, None
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                return None, JSONResponse(
                    {"ok": False, "error": "Expected a JSON object"},
                    status_code=400,
                )
            return body, None
        except (json.JSONDecodeError, ValueError):
            return {}, None

    # ── Repo path validation helper ────────────────────────

    def _validate_merged_config(merged: dict) -> JSONResponse | None:
        """Validate repo_path in the merged config dict."""
        repo_path = merged.get("repo_path", ".")
        err = _validate_repo_path(repo_path)
        if err:
            return JSONResponse({"ok": False, "error": err}, status_code=400)
        return None

    # ── App instance ────────────────────────────────────────────────────

    app = FastAPI(
        title="ReleasePilot",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        root_path=root_path,
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS middleware — restrict to configured origins
    cors_origins = os.environ.get("RELEASEPILOT_CORS_ORIGINS", "").strip()
    if cors_origins:
        from starlette.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins.split(","),
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
        )

    # ── Routes ──────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_page(request: Request) -> HTMLResponse:
        """Serve the self-contained interactive HTML dashboard."""
        nonce = request.state.csp_nonce
        if state.last_dashboard_html is None:
            try:
                html = await asyncio.to_thread(_generate_dashboard_html, state.config)
                state.last_dashboard_html = html
            except Exception as exc:
                logger.exception("Dashboard generation failed")
                from html import escape as _esc

                return HTMLResponse(
                    f"<html><body><h1>Dashboard Error</h1><p>{_esc(str(exc))}</p></body></html>",
                    status_code=500,
                )
        html = _inject_csp_nonce(state.last_dashboard_html, nonce)
        return HTMLResponse(html)

    @app.get("/health/live")
    async def health_live() -> dict:
        return {"status": "alive"}

    @app.get("/health/ready")
    async def health_ready() -> Response:
        # report 503 if startup generation failed
        if _startup_generation_failed:
            return JSONResponse(
                {"status": "not_ready", "reason": "startup_generation_failed"},
                status_code=503,
            )
        if state.analysis_progress.phase == AnalysisPhase.RUNNING:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready"}, status_code=200)

    @app.get("/api/status")
    async def api_status() -> dict:
        uptime_s = round(time.monotonic() - start_time, 1)
        return {
            "version": __version__,
            "uptime_seconds": uptime_s,
            "analysis": state.analysis_progress.to_dict(),
            "git_available": _check_git_available(),
        }

    # ── Generate ────────────────────────────────────────────────────────

    @app.post("/api/generate")
    async def api_generate(request: Request) -> Response:
        """Trigger asynchronous release-notes generation."""
        # Auth check
        auth_err = _check_auth(request)
        if auth_err:
            return auth_err

        # Rate limit
        rate_err = _check_rate_limit(request)
        if rate_err:
            return rate_err

        # Body with size limit
        body, body_err = await _read_json_body(request)
        if body_err:
            return body_err

        merged = {**state.config, **(body or {})}

        # Validate repo_path
        path_err = _validate_merged_config(merged)
        if path_err:
            return path_err

        async with state.analysis_lock:
            if state.analysis_progress.phase == AnalysisPhase.RUNNING:
                return JSONResponse(
                    {"ok": False, "error": "Generation already in progress"}, status_code=409
                )
            state.analysis_progress = AnalysisProgress(
                phase=AnalysisPhase.RUNNING, started_at=time.time()
            )

        task = asyncio.create_task(_run_generation(merged))
        _background_tasks.append(task)
        return JSONResponse({"ok": True, "message": "Generation started"})

    async def _run_generation(cfg: dict) -> None:
        """Execute the generation pipeline in a thread and broadcast progress."""
        from releasepilot.pipeline.orchestrator import PipelineError
        from releasepilot.pipeline.orchestrator import generate as pipeline_generate

        settings = _build_settings_from_config(cfg)
        loop = asyncio.get_running_loop()

        def progress_callback(
            stage: str, detail: str = "", current: int = 0, total: int = 0
        ) -> None:
            state.analysis_progress.stage = stage
            state.analysis_progress.detail = detail
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(
                    state.broadcast(
                        "generation_progress",
                        {"stage": stage, "detail": detail, "current": current, "total": total},
                    )
                )
            )

        try:
            # timeout on pipeline execution
            output = await asyncio.wait_for(
                asyncio.to_thread(pipeline_generate, settings, progress_callback),
                timeout=GENERATION_TIMEOUT_SECONDS,
            )
            state.last_result = {
                "output": output,
                "audience": settings.audience.value,
                "format": settings.output_format.value,
                "generated_at": time.time(),
            }
            state.analysis_progress.phase = AnalysisPhase.COMPLETED
            state.analysis_progress.completed_at = time.time()
            await state.broadcast(
                "generation_complete",
                {"audience": settings.audience.value, "format": settings.output_format.value},
            )
        except TimeoutError:
            state.analysis_progress.phase = AnalysisPhase.FAILED
            state.analysis_progress.error = (
                f"Generation timed out after {GENERATION_TIMEOUT_SECONDS}s"
            )
            await state.broadcast("generation_failed", {"error": state.analysis_progress.error})
        except PipelineError as exc:
            state.analysis_progress.phase = AnalysisPhase.FAILED
            state.analysis_progress.error = str(exc)
            await state.broadcast("generation_failed", {"error": str(exc)})
        except Exception as exc:
            logger.exception("Unexpected generation error")
            state.analysis_progress.phase = AnalysisPhase.FAILED
            state.analysis_progress.error = str(exc)
            await state.broadcast("generation_failed", {"error": str(exc)})

    @app.get("/api/generate/stream")
    async def api_generate_stream() -> StreamingResponse:
        """SSE endpoint for real-time generation progress."""
        queue = state.subscribe()

        async def event_generator():
            try:
                yield _sse_format("current_state", state.analysis_progress.to_dict())
                while True:
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield _sse_format(msg["event"], msg["data"])
                        if msg["event"] in ("generation_complete", "generation_failed"):
                            break
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                state.unsubscribe(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/generate/results")
    async def api_generate_results() -> Response:
        """Return the latest generation results."""
        if state.last_result is None:
            return JSONResponse({"ok": False, "error": "No results available"}, status_code=404)
        return JSONResponse({"ok": True, **state.last_result})

    # ── Dashboard ───────────────────────────────────────────────────────

    @app.post("/api/dashboard")
    async def api_dashboard_regenerate(request: Request) -> Response:
        """Trigger dashboard regeneration."""
        # Auth check
        auth_err = _check_auth(request)
        if auth_err:
            return auth_err

        # Rate limit
        rate_err = _check_rate_limit(request)
        if rate_err:
            return rate_err

        body, body_err = await _read_json_body(request)
        if body_err:
            return body_err

        merged = {**state.config, **(body or {})}

        # Validate repo_path
        path_err = _validate_merged_config(merged)
        if path_err:
            return path_err

        try:
            html, data_dict = await asyncio.to_thread(
                _generate_dashboard_full,
                merged,
            )
            state.last_dashboard_html = html
            return JSONResponse({"ok": True, "data": data_dict})
        except Exception as exc:
            logger.exception("Dashboard regeneration failed")
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    @app.get("/api/dashboard/html", response_class=HTMLResponse)
    async def api_dashboard_html(request: Request) -> HTMLResponse:
        """Return the raw self-contained HTML dashboard (for export)."""
        nonce = request.state.csp_nonce
        if state.last_dashboard_html is None:
            try:
                html = await asyncio.to_thread(_generate_dashboard_html, state.config)
                state.last_dashboard_html = html
            except Exception as exc:
                from html import escape as _esc

                return HTMLResponse(
                    f"<html><body><h1>Error</h1><p>{_esc(str(exc))}</p></body></html>",
                    status_code=500,
                )
        return HTMLResponse(_inject_csp_nonce(state.last_dashboard_html, nonce))

    # ── Config ──────────────────────────────────────────────────────────

    @app.get("/api/config")
    async def api_config_get() -> dict:
        """Return current configuration."""
        cfg = {
            "repo_path": state.config.get("repo_path", "."),
            "from_ref": state.config.get("from_ref", ""),
            "to_ref": state.config.get("to_ref", "HEAD"),
            "branch": state.config.get("branch", ""),
            "since_date": state.config.get("since_date", ""),
            "audience": state.config.get("audience", "changelog"),
            "format": state.config.get("output_format", state.config.get("format", "markdown")),
            "language": state.config.get("language", "en"),
            "app_name": state.config.get("app_name", ""),
            "version": state.config.get("version", ""),
            "title": state.config.get("title", ""),
            "source_type": state.config.get("source_type", "local"),
        }
        # Include GitLab config (token masked)
        if state.config.get("gitlab_url"):
            cfg["gitlab_url"] = state.config["gitlab_url"]
        if state.config.get("gitlab_project"):
            cfg["gitlab_project"] = state.config["gitlab_project"]
        if state.config.get("gitlab_token"):
            cfg["gitlab_token_set"] = True
        # Include GitHub config (token masked)
        if state.config.get("github_owner"):
            cfg["github_owner"] = state.config["github_owner"]
        if state.config.get("github_repo"):
            cfg["github_repo"] = state.config["github_repo"]
        if state.config.get("github_url"):
            cfg["github_url"] = state.config["github_url"]
        if state.config.get("github_token"):
            cfg["github_token_set"] = True
        return cfg

    @app.put("/api/config")
    async def api_config_update(request: Request) -> Response:
        """Update configuration fields."""
        # Auth check
        auth_err = _check_auth(request)
        if auth_err:
            return auth_err

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "error": "Expected a JSON object"}, status_code=400)

        allowed = {
            "repo_path",
            "from_ref",
            "to_ref",
            "branch",
            "since_date",
            "audience",
            "format",
            "output_format",
            "language",
            "app_name",
            "version",
            "title",
            "gitlab_url",
            "gitlab_token",
            "gitlab_project",
            "gitlab_ssl_verify",
            "github_token",
            "github_owner",
            "github_repo",
            "github_url",
            "github_ssl_verify",
            "source_type",
        }
        # Validate enum-like fields before accepting
        _valid_audiences = {
            "technical",
            "user",
            "summary",
            "changelog",
            "customer",
            "executive",
            "narrative",
            "customer-narrative",
        }
        _valid_formats = {"markdown", "plaintext", "json", "pdf", "docx"}
        _valid_languages = {"en", "pl", "de", "fr", "es", "it", "pt", "nl", "uk", "cs"}

        _bool_fields = {"gitlab_ssl_verify", "github_ssl_verify"}

        for key, value in body.items():
            if key not in allowed:
                continue
            if key in _bool_fields:
                if not isinstance(value, bool):
                    return JSONResponse(
                        {"ok": False, "error": f"Field '{key}' must be a boolean"}, status_code=400
                    )
            elif not isinstance(value, str):
                return JSONResponse(
                    {"ok": False, "error": f"Field '{key}' must be a string"}, status_code=400
                )
            if key == "audience" and value not in _valid_audiences:
                return JSONResponse(
                    {"ok": False, "error": f"Invalid audience: '{value}'"}, status_code=400
                )
            if key in ("format", "output_format") and value not in _valid_formats:
                return JSONResponse(
                    {"ok": False, "error": f"Invalid format: '{value}'"}, status_code=400
                )
            if key == "language" and value not in _valid_languages:
                return JSONResponse(
                    {"ok": False, "error": f"Invalid language: '{value}'"}, status_code=400
                )
            if key == "since_date" and value:
                import re as _re

                if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    return JSONResponse(
                        {"ok": False, "error": "since_date must be YYYY-MM-DD format"},
                        status_code=400,
                    )
            # validate repo_path
            if key == "repo_path":
                err = _validate_repo_path(value)
                if err:
                    return JSONResponse({"ok": False, "error": err}, status_code=400)
            state.config[key] = value

        # Invalidate cached dashboard on config change
        state.last_dashboard_html = None

        return JSONResponse({"ok": True, "config": await api_config_get()})

    # ── Favicon ─────────────────────────────────────────────────────────

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(content=_FAVICON_PNG, media_type="image/png")

    # ── Include extracted route modules ─────────────────────────────────

    from releasepilot.web.routes_github import router as github_router
    from releasepilot.web.routes_gitlab import router as gitlab_router
    from releasepilot.web.routes_wizard import router as wizard_router

    app.include_router(gitlab_router)
    app.include_router(github_router)
    app.include_router(wizard_router)

    # Expose shared state on app.state for route modules
    app.state.app_state = state
    app.state.api_key = api_key
    app.state.rate_buckets = _rate_buckets

    # ── Wizard Generate (stays here — needs _background_tasks) ─────────

    @app.post("/api/wizard/generate")
    async def api_wizard_generate(request: Request) -> Response:
        """Generate release notes from the wizard configuration."""
        auth_err = _check_auth(request)
        if auth_err:
            return auth_err

        rate_err = _check_rate_limit(request)
        if rate_err:
            return rate_err

        if not state.wizard.repositories:
            return JSONResponse(
                {"ok": False, "error": "No repositories configured. Add at least one repository."},
                status_code=400,
            )

        for repo in state.wizard.repositories:
            if repo.source_type in ("github", "gitlab") and repo.requires_token:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": f"Repository '{repo.display_name}' requires authentication. "
                        "Provide a token.",
                    },
                    status_code=400,
                )

        async with state.analysis_lock:
            if state.analysis_progress.phase == AnalysisPhase.RUNNING:
                return JSONResponse(
                    {"ok": False, "error": "Generation already in progress"},
                    status_code=409,
                )
            state.analysis_progress = AnalysisProgress(
                phase=AnalysisPhase.RUNNING, started_at=time.time()
            )

        gen_config = {**state.config, **state.wizard.to_generation_config()}
        state.wizard.step = WizardStep.GENERATING

        task = asyncio.create_task(_run_generation(gen_config))
        _background_tasks.append(task)
        return JSONResponse(
            {
                "ok": True,
                "message": "Generation started",
                "repository_count": len(state.wizard.repositories),
                "source_type": state.wizard.source_type,
            }
        )

    return app
