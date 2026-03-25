"""Shared helpers for the web server routes.

Extracted from server.py to reduce file size and separate concerns.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from releasepilot.shared.logging import get_logger

logger = get_logger("web.helpers")

# ── Constants ──────────────────────────────────────────────────────────────

MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024
GENERATION_TIMEOUT_SECONDS = 300
_RATE_LIMIT_MAX = 30
_RATE_LIMIT_WINDOW = 60  # seconds

_REPO_PATH_UNSAFE_RE = re.compile(r"[;|&`$(){}\[\]!#~]")


# ── Validation ─────────────────────────────────────────────────────────────


def validate_repo_path(path: str) -> str | None:
    """Validate repo_path for safety. Returns error message or None if valid."""
    if not path or path == ".":
        return None
    if _REPO_PATH_UNSAFE_RE.search(path):
        return f"repo_path contains unsafe characters: '{path}'"
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        return f"repo_path does not exist or is not a directory: '{path}'"
    return None


def check_git_available() -> bool:
    """Return True if the git binary is available on PATH."""
    return shutil.which("git") is not None


# ── Request helpers ────────────────────────────────────────────────────────


async def read_json_body(request: Request) -> tuple[dict | None, JSONResponse | None]:
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


def check_auth(request: Request) -> JSONResponse | None:
    """Return a 401 response if auth is enabled and the key is wrong."""
    api_key = getattr(request.app.state, "api_key", "")
    if not api_key:
        return None
    header = request.headers.get("Authorization", "")
    if header == f"Bearer {api_key}":
        return None
    return JSONResponse(
        {"ok": False, "error": "Unauthorized"},
        status_code=401,
    )


def check_rate_limit(request: Request) -> JSONResponse | None:
    """Return a 429 response if the client exceeded the rate limit."""
    import time

    buckets = getattr(request.app.state, "rate_buckets", {})
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = buckets.setdefault(client_ip, [])
    cutoff = now - _RATE_LIMIT_WINDOW
    buckets[client_ip] = bucket = [t for t in bucket if t > cutoff]
    if len(bucket) >= _RATE_LIMIT_MAX:
        return JSONResponse(
            {"ok": False, "error": "Rate limit exceeded"},
            status_code=429,
        )
    bucket.append(now)
    return None


def get_app_state(request: Request) -> Any:
    """Get the AppState from the request's app."""
    return request.app.state.app_state


def validate_merged_config(merged: dict) -> JSONResponse | None:
    """Validate repo_path in the merged config dict."""
    repo_path = merged.get("repo_path", ".")
    err = validate_repo_path(repo_path)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    return None


# ── Settings Builder ───────────────────────────────────────────────────────


def build_settings_from_config(config: dict) -> Any:
    """Build a Settings object from a config dict.

    Separated from server.py for reuse across route modules.
    """
    from releasepilot.config.settings import Settings

    source_type = config.get("source_type", "")
    multi_sources = config.get("multi_repo_sources")
    if multi_sources and isinstance(multi_sources, list) and len(multi_sources) > 0:
        return Settings(
            repo_path=config.get("repo_path", "."),
            multi_repo_sources=tuple(multi_sources),
            language=config.get("language", "en"),
            since_date=config.get("since_date", ""),
            from_ref=config.get("from_ref", ""),
            to_ref=config.get("to_ref", "HEAD"),
            branch=config.get("branch", ""),
        )

    base_kwargs: dict[str, Any] = {
        "repo_path": config.get("repo_path", "."),
        "language": config.get("language", "en"),
        "since_date": config.get("since_date", ""),
        "from_ref": config.get("from_ref", ""),
        "to_ref": config.get("to_ref", "HEAD"),
        "branch": config.get("branch", ""),
    }

    if source_type == "gitlab":
        base_kwargs.update(
            gitlab_url=config.get("gitlab_url", ""),
            gitlab_token=config.get("gitlab_token", ""),
            gitlab_project=config.get("gitlab_project", ""),
            gitlab_ssl_verify=config.get("gitlab_ssl_verify", True),
        )
    elif source_type == "github":
        base_kwargs.update(
            github_token=config.get("github_token", ""),
            github_owner=config.get("github_owner", ""),
            github_repo=config.get("github_repo", ""),
            github_url=config.get("github_url", "https://api.github.com"),
            github_ssl_verify=config.get("github_ssl_verify", True),
        )

    return Settings(**base_kwargs)
