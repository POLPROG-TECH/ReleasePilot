"""Wizard routes for multi-source release note generation.

Extracted from server.py — handles /api/wizard/* endpoints
and /api/sources/* and /api/scan-directory.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from releasepilot.shared.logging import get_logger
from releasepilot.web.server_helpers import (
    check_auth,
    check_rate_limit,
    read_json_body,
    validate_repo_path,
)
from releasepilot.web.state import WizardRepository, WizardStep

logger = get_logger("web.routes_wizard")

router = APIRouter(tags=["wizard"])


# ── Source Validation ──────────────────────────────────────────────────────


@router.post("/api/sources/validate")
async def api_validate_source(request: Request) -> Response:
    """Validate a repository source URL."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    body = body or {}
    url = body.get("url", "")
    if not url:
        return JSONResponse(
            {"ok": False, "error": "Missing 'url' field"},
            status_code=400,
        )

    from releasepilot.sources.factory import validate_repo_source

    result = await asyncio.to_thread(
        validate_repo_source,
        url,
        provider=body.get("provider", ""),
        token=body.get("token", ""),
        app_label=body.get("app_label", ""),
    )

    if not result.valid:
        return JSONResponse(
            {"ok": False, "error": result.error, "provider": result.provider},
            status_code=400,
        )

    return JSONResponse(
        {
            "ok": True,
            "provider": result.provider,
            "source_type": result.source_type,
            "owner": result.owner,
            "repo": result.repo,
            "project_path": result.project_path,
            "display_name": result.display_name,
            "is_org": result.is_org,
            "org_name": result.org_name,
        }
    )


# ── Directory Scanning ─────────────────────────────────────────────────────


@router.post("/api/scan-directory")
async def api_scan_directory(request: Request) -> Response:
    """Scan a directory for git repositories."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    body = body or {}
    raw_path = body.get("path", "").strip()
    if not raw_path:
        return JSONResponse(
            {"ok": False, "error": "Missing 'path' field"},
            status_code=400,
        )

    path_err = validate_repo_path(raw_path)
    if path_err:
        return JSONResponse({"ok": False, "error": path_err}, status_code=400)

    resolved = Path(raw_path).resolve()
    if not resolved.is_dir():
        return JSONResponse(
            {"ok": False, "error": f"Not a directory: {raw_path}"},
            status_code=400,
        )

    repos: list[dict[str, str]] = []
    if (resolved / ".git").is_dir():
        name = resolved.name or str(resolved)
        repos.append({"name": name, "path": str(resolved)})

    try:
        for child in sorted(resolved.iterdir()):
            if child.is_dir() and (child / ".git").is_dir():
                repos.append({"name": child.name, "path": str(child)})
    except PermissionError:
        return JSONResponse(
            {"ok": False, "error": f"Permission denied reading: {raw_path}"},
            status_code=403,
        )

    if not repos:
        return JSONResponse(
            {"ok": False, "error": f"No git repositories found in: {raw_path}"},
            status_code=404,
        )

    return JSONResponse({"ok": True, "repos": repos, "count": len(repos)})


# ── Wizard State ───────────────────────────────────────────────────────────


@router.get("/api/wizard/state")
async def api_wizard_state(request: Request) -> dict:
    """Return the current wizard session state."""
    state = request.app.state.app_state
    return {"ok": True, **state.wizard.to_dict()}


@router.post("/api/wizard/reset")
async def api_wizard_reset(request: Request) -> Response:
    """Reset the wizard to start a new session."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    state = request.app.state.app_state
    state.wizard.reset()
    return JSONResponse({"ok": True, **state.wizard.to_dict()})


@router.put("/api/wizard/source-type")
async def api_wizard_source_type(request: Request) -> Response:
    """Set the wizard source type (local or remote)."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    source_type = (body or {}).get("source_type", "")
    if source_type not in ("local", "remote"):
        return JSONResponse(
            {"ok": False, "error": "source_type must be 'local' or 'remote'"},
            status_code=400,
        )

    state = request.app.state.app_state
    state.wizard.source_type = source_type
    state.wizard.step = WizardStep.REPOSITORIES
    return JSONResponse({"ok": True, **state.wizard.to_dict()})


@router.post("/api/wizard/repositories")
async def api_wizard_add_repository(request: Request) -> Response:
    """Add a repository to the wizard session."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    rate_err = check_rate_limit(request)
    if rate_err:
        return rate_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    body = body or {}
    source_type = body.get("source_type", "")
    url_or_path = body.get("url", body.get("path", ""))
    token = body.get("token", "")
    app_label = body.get("app_label", "")
    verify_ssl = body.get("verify_ssl", True)

    if not url_or_path:
        return JSONResponse(
            {"ok": False, "error": "Missing 'url' or 'path' field"},
            status_code=400,
        )

    from releasepilot.sources.factory import validate_repo_source

    validation = await asyncio.to_thread(
        validate_repo_source,
        url_or_path,
        provider=source_type if source_type in ("github", "gitlab") else "",
        token=token,
        app_label=app_label,
    )

    if not validation.valid:
        return JSONResponse(
            {"ok": False, "error": validation.error, "provider": validation.provider},
            status_code=400,
        )

    repo = WizardRepository(
        source_type=validation.source_type,
        url=url_or_path,
        owner=validation.owner,
        repo=validation.repo,
        project_path=validation.project_path,
        app_label=app_label or validation.display_name,
        token=token,
        verify_ssl=verify_ssl,
        validated=True,
        accessible=True,
    )

    if validation.source_type in ("github", "gitlab"):
        inspection = await _wizard_inspect_remote(request, repo)
        if inspection:
            repo.default_branch = inspection.get("default_branch", "")
            repo.branches = [b["name"] for b in inspection.get("branches", [])]
            repo.tags = [t["name"] for t in inspection.get("tags", [])]
            repo.accessible = inspection.get("is_accessible", False)
            if not repo.accessible:
                repo.error = inspection.get("error", "Repository not accessible")

    state = request.app.state.app_state
    add_err = state.wizard.add_repository(repo)
    if add_err:
        return JSONResponse({"ok": False, "error": add_err}, status_code=400)

    return JSONResponse(
        {
            "ok": True,
            "repository": repo.to_dict(),
            "repository_count": len(state.wizard.repositories),
        }
    )


async def _wizard_inspect_remote(request: Request, repo: WizardRepository) -> dict | None:
    """Inspect a remote repository and return basic metadata."""
    config = request.app.state.app_state.config
    try:
        if repo.source_type == "github":
            from releasepilot.sources.github import GitHubClient
            from releasepilot.sources.github_inspector import GitHubInspector

            gh_token = (
                repo.token
                or config.get("github_token", "")
                or os.environ.get("RELEASEPILOT_GITHUB_TOKEN", "")
            )
            client = GitHubClient(token=gh_token, verify_ssl=repo.verify_ssl)
            inspector = GitHubInspector(client)
            result = await asyncio.to_thread(inspector.inspect, repo.owner, repo.repo)
            return {
                "is_accessible": result.is_accessible,
                "default_branch": result.default_branch,
                "branches": [{"name": b.name, "commit": b.commit_sha[:8]} for b in result.branches],
                "tags": [{"name": t.name, "commit": t.commit_sha[:8]} for t in result.tags],
                "error": result.error,
            }

        if repo.source_type == "gitlab":
            from releasepilot.sources.gitlab import GitLabClient
            from releasepilot.sources.gitlab_inspector import GitLabInspector

            gl_token = (
                repo.token
                or config.get("gitlab_token", "")
                or os.environ.get("RELEASEPILOT_GITLAB_TOKEN", "")
            )
            gl_url = ""
            if "://" in repo.url:
                parts = repo.url.split("://", 1)
                domain = parts[1].split("/", 1)[0]
                gl_url = f"{parts[0]}://{domain}"

            if not gl_url:
                return {"is_accessible": False, "error": "Cannot determine GitLab URL"}

            client = GitLabClient(base_url=gl_url, token=gl_token, verify_ssl=repo.verify_ssl)
            inspector = GitLabInspector(client)
            result = await asyncio.to_thread(inspector.inspect, repo.project_path)
            return {
                "is_accessible": result.is_accessible,
                "default_branch": result.default_branch,
                "branches": [{"name": b.name, "commit": b.commit_sha[:8]} for b in result.branches],
                "tags": [{"name": t.name, "commit": t.commit_sha[:8]} for t in result.tags],
                "error": result.error,
            }
    except Exception as exc:
        logger.warning("Wizard remote inspection failed: %s", exc)
        return {"is_accessible": False, "error": str(exc)}

    return None


@router.delete("/api/wizard/repositories/{repo_id}")
async def api_wizard_remove_repository(repo_id: str, request: Request) -> Response:
    """Remove a repository from the wizard session."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    state = request.app.state.app_state
    removed = state.wizard.remove_repository(repo_id)
    if not removed:
        return JSONResponse(
            {"ok": False, "error": f"Repository '{repo_id}' not found"},
            status_code=404,
        )

    return JSONResponse({"ok": True, "repository_count": len(state.wizard.repositories)})


@router.get("/api/wizard/repositories")
async def api_wizard_list_repositories(request: Request) -> dict:
    """List all repositories in the current wizard session."""
    state = request.app.state.app_state
    return {
        "ok": True,
        "repositories": [r.to_dict() for r in state.wizard.repositories],
        "repository_count": len(state.wizard.repositories),
        "source_type": state.wizard.source_type,
    }


@router.put("/api/wizard/release-range")
async def api_wizard_release_range(request: Request) -> Response:
    """Set the shared release range/scope for all repositories."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    body = body or {}

    since = body.get("since_date", "")
    if since:
        import re as _re

        if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
            return JSONResponse(
                {"ok": False, "error": "since_date must be YYYY-MM-DD format"},
                status_code=400,
            )

    state = request.app.state.app_state
    if "from_ref" in body:
        state.wizard.from_ref = body["from_ref"]
    if "to_ref" in body:
        state.wizard.to_ref = body["to_ref"]
    if "since_date" in body:
        state.wizard.since_date = body["since_date"]
    if "branch" in body:
        state.wizard.branch = body["branch"]

    state.wizard.step = WizardStep.AUDIENCE
    return JSONResponse({"ok": True, **state.wizard.to_dict()})


@router.put("/api/wizard/options")
async def api_wizard_options(request: Request) -> Response:
    """Set generation options for the wizard."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    body = body or {}

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

    state = request.app.state.app_state

    if "audience" in body:
        if body["audience"] not in _valid_audiences:
            return JSONResponse(
                {"ok": False, "error": f"Invalid audience: '{body['audience']}'"},
                status_code=400,
            )
        state.wizard.audience = body["audience"]

    if "output_format" in body:
        if body["output_format"] not in _valid_formats:
            return JSONResponse(
                {"ok": False, "error": f"Invalid format: '{body['output_format']}'"},
                status_code=400,
            )
        state.wizard.output_format = body["output_format"]

    if "language" in body:
        if body["language"] not in _valid_languages:
            return JSONResponse(
                {"ok": False, "error": f"Invalid language: '{body['language']}'"},
                status_code=400,
            )
        state.wizard.language = body["language"]

    for field in ("app_name", "version", "title"):
        if field in body and isinstance(body[field], str):
            setattr(state.wizard, field, body[field])

    state.wizard.step = WizardStep.REVIEW
    return JSONResponse({"ok": True, **state.wizard.to_dict()})


@router.post("/api/wizard/validate-url")
async def api_wizard_validate_url(request: Request) -> Response:
    """Validate a repository URL without adding it to the wizard."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    body = body or {}
    url = body.get("url", "")
    if not url:
        return JSONResponse(
            {"ok": False, "error": "Missing 'url' field"},
            status_code=400,
        )

    from releasepilot.sources.factory import validate_repo_source

    result = await asyncio.to_thread(
        validate_repo_source,
        url,
        provider=body.get("provider", ""),
        token=body.get("token", ""),
        app_label=body.get("app_label", ""),
    )

    return JSONResponse(
        {
            "ok": result.valid,
            "provider": result.provider,
            "source_type": result.source_type,
            "display_name": result.display_name,
            "owner": result.owner,
            "repo": result.repo,
            "project_path": result.project_path,
            "requires_token": result.requires_token,
            "error": result.error,
        }
    )


# ── Wizard Dashboard Generation ───────────────────────────────────────────


@router.post("/api/wizard/dashboard")
async def api_wizard_dashboard(request: Request) -> Response:
    """Generate dashboard data using the wizard's stored state.

    Unlike ``/api/dashboard`` (which relies on ``state.config``), this
    endpoint builds the pipeline configuration from the wizard session —
    ensuring the selected repositories (local **or** remote) are the
    actual source of truth for commit collection and generation.
    """
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    rate_err = check_rate_limit(request)
    if rate_err:
        return rate_err

    state = request.app.state.app_state

    if not state.wizard.repositories:
        return JSONResponse(
            {"ok": False, "error": "No repositories configured in the wizard."},
            status_code=400,
        )

    # Build config from wizard state — this correctly sets github_owner,
    # github_repo, github_token, gitlab_*, multi_repo_sources, etc.
    gen_config = {**state.config, **state.wizard.to_generation_config()}

    from releasepilot.web.server import _generate_dashboard_full

    try:
        html, data_dict = await asyncio.to_thread(_generate_dashboard_full, gen_config)
        state.last_dashboard_html = html
        return JSONResponse({"ok": True, "data": data_dict})
    except Exception as exc:
        logger.exception("Wizard dashboard generation failed")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
