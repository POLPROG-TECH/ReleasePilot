"""GitLab integration routes.

Extracted from server.py — handles /api/gitlab/* endpoints.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from releasepilot.shared.logging import get_logger
from releasepilot.web.server_helpers import check_auth, check_rate_limit, read_json_body

logger = get_logger("web.routes_gitlab")

router = APIRouter(prefix="/api/gitlab", tags=["gitlab"])


def _get_gitlab_inspector(config: dict) -> tuple[Any, JSONResponse | None]:
    """Create a GitLabInspector from config or env."""
    from releasepilot.sources.gitlab import GitLabError
    from releasepilot.sources.gitlab_inspector import GitLabInspector

    gitlab_url = config.get(
        "gitlab_url",
        os.environ.get("RELEASEPILOT_GITLAB_URL", ""),
    )
    gitlab_token = config.get(
        "gitlab_token",
        os.environ.get("RELEASEPILOT_GITLAB_TOKEN", ""),
    )
    verify_ssl = config.get("gitlab_ssl_verify", True)

    if not gitlab_url:
        return None, JSONResponse(
            {
                "ok": False,
                "error": "GitLab URL not configured. "
                "Set gitlab_url in config or RELEASEPILOT_GITLAB_URL env var.",
            },
            status_code=400,
        )
    if not gitlab_token:
        return None, JSONResponse(
            {
                "ok": False,
                "error": "GitLab token not configured. "
                "Set gitlab_token in config or RELEASEPILOT_GITLAB_TOKEN env var.",
            },
            status_code=400,
        )

    try:
        inspector = GitLabInspector.from_config(
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token,
            verify_ssl=verify_ssl,
        )
        return inspector, None
    except GitLabError as exc:
        return None, JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=400,
        )


@router.post("/validate")
async def api_gitlab_validate(request: Request) -> Response:
    """Validate GitLab connection and token."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    config = request.app.state.app_state.config
    if body:
        for key in ("gitlab_url", "gitlab_token", "gitlab_ssl_verify"):
            if key in body:
                config[key] = body[key]

    inspector, err = _get_gitlab_inspector(config)
    if err:
        return err

    from releasepilot.sources.gitlab import GitLabError

    try:
        result = await asyncio.to_thread(inspector._client.validate_token)
        return JSONResponse(
            {
                "ok": True,
                "user": result.get("username", ""),
                "name": result.get("name", ""),
                "message": f"Authenticated as {result.get('username', 'unknown')}",
            }
        )
    except GitLabError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=401 if exc.is_auth_error else 502,
        )


@router.post("/inspect")
async def api_gitlab_inspect(request: Request) -> Response:
    """Inspect a remote GitLab project."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    rate_err = check_rate_limit(request)
    if rate_err:
        return rate_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    project_path = (body or {}).get("project", "")
    if not project_path:
        return JSONResponse(
            {"ok": False, "error": "Missing 'project' field (e.g. 'group/repo')"},
            status_code=400,
        )

    config = request.app.state.app_state.config
    inspector, err = _get_gitlab_inspector(config)
    if err:
        return err

    result = await asyncio.to_thread(inspector.inspect, project_path)

    response: dict[str, Any] = {
        "ok": result.is_accessible,
        "is_authenticated": result.is_authenticated,
        "is_accessible": result.is_accessible,
        "default_branch": result.default_branch,
        "diagnostics": list(result.diagnostics),
    }

    if result.project:
        response["project"] = {
            "id": result.project.id,
            "name": result.project.name,
            "path": result.project.path_with_namespace,
            "web_url": result.project.web_url,
            "visibility": result.project.visibility,
        }

    if result.branches:
        response["branches"] = [
            {"name": b.name, "commit": b.commit_sha[:8], "default": b.is_default}
            for b in result.branches
        ]

    if result.tags:
        response["tags"] = [{"name": t.name, "commit": t.commit_sha[:8]} for t in result.tags]

    if result.error:
        response["error"] = result.error
        response["error_kind"] = result.error_kind

    status = 200 if result.is_accessible else (401 if not result.is_authenticated else 404)
    return JSONResponse(response, status_code=status)


@router.get("/branches/{project_id}")
async def api_gitlab_branches(project_id: int, request: Request) -> Response:
    """List branches for a GitLab project."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    config = request.app.state.app_state.config
    inspector, err = _get_gitlab_inspector(config)
    if err:
        return err

    from releasepilot.sources.gitlab import GitLabError

    try:
        branches = await asyncio.to_thread(inspector._client.list_branches, project_id)
        return JSONResponse(
            {
                "ok": True,
                "count": len(branches),
                "branches": [
                    {
                        "name": b.name,
                        "commit": b.commit_sha[:8],
                        "date": b.commit_date,
                        "default": b.is_default,
                        "protected": b.is_protected,
                    }
                    for b in branches
                ],
            }
        )
    except GitLabError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=502,
        )


@router.get("/branch/{project_id}/{branch_name:path}")
async def api_gitlab_branch_lookup(
    project_id: int,
    branch_name: str,
    request: Request,
) -> Response:
    """Look up a specific branch."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    config = request.app.state.app_state.config
    inspector, err = _get_gitlab_inspector(config)
    if err:
        return err

    result = await asyncio.to_thread(inspector.lookup_branch, project_id, branch_name)

    if result.found and result.branch:
        return JSONResponse(
            {
                "ok": True,
                "found": True,
                "branch": {
                    "name": result.branch.name,
                    "commit": result.branch.commit_sha,
                    "date": result.branch.commit_date,
                    "default": result.branch.is_default,
                    "protected": result.branch.is_protected,
                },
            }
        )
    return JSONResponse(
        {
            "ok": True,
            "found": False,
            "error": result.error,
            "error_kind": result.error_kind,
        },
        status_code=200,
    )


@router.get("/tags/{project_id}")
async def api_gitlab_tags(project_id: int, request: Request) -> Response:
    """List tags for a GitLab project."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    config = request.app.state.app_state.config
    inspector, err = _get_gitlab_inspector(config)
    if err:
        return err

    from releasepilot.sources.gitlab import GitLabError

    try:
        tags = await asyncio.to_thread(inspector._client.list_tags, project_id)
        return JSONResponse(
            {
                "ok": True,
                "count": len(tags),
                "tags": [
                    {"name": t.name, "commit": t.commit_sha[:8], "date": t.commit_date}
                    for t in tags
                ],
            }
        )
    except GitLabError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=502,
        )


# ── Group Project Discovery ──────────────────────────────────────────


@router.post("/group-repos")
async def api_gitlab_group_repos(request: Request) -> Response:
    """List projects under a GitLab group (including subgroups)."""
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
    group = body.get("group", "").strip()
    if not group:
        return JSONResponse({"ok": False, "error": "Missing 'group' field"}, status_code=400)

    config = request.app.state.app_state.config
    base_url = (
        body.get("gitlab_url", "")
        or config.get("gitlab_url", "")
        or os.environ.get("RELEASEPILOT_GITLAB_URL", "https://gitlab.com")
    )
    token = (
        body.get("token", "")
        or config.get("gitlab_token", "")
        or os.environ.get("RELEASEPILOT_GITLAB_TOKEN", "")
    )

    from releasepilot.sources.gitlab import GitLabClient, GitLabError

    try:
        client = GitLabClient(base_url=base_url, token=token)
        projects = await asyncio.to_thread(client.list_group_projects, group)
        return JSONResponse(
            {
                "ok": True,
                "group": group,
                "count": len(projects),
                "repos": [
                    {
                        "name": p.name,
                        "full_name": p.path_with_namespace,
                        "url": p.web_url,
                        "default_branch": p.default_branch,
                        "visibility": p.visibility,
                        "description": p.description,
                    }
                    for p in projects
                ],
            }
        )
    except GitLabError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=502,
        )
