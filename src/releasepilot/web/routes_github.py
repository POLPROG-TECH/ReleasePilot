"""GitHub integration routes.

Extracted from server.py — handles /api/github/* endpoints.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from releasepilot.shared.logging import get_logger
from releasepilot.web.server_helpers import check_auth, check_rate_limit, read_json_body

logger = get_logger("web.routes_github")

router = APIRouter(prefix="/api/github", tags=["github"])


def _get_github_inspector(config: dict) -> tuple[Any, JSONResponse | None]:
    """Create a GitHubInspector from config or env."""
    from releasepilot.sources.github import GitHubError
    from releasepilot.sources.github_inspector import GitHubInspector

    github_token = config.get(
        "github_token",
        os.environ.get("RELEASEPILOT_GITHUB_TOKEN", ""),
    )
    github_url = config.get(
        "github_url",
        os.environ.get("RELEASEPILOT_GITHUB_URL", "https://api.github.com"),
    )

    if not github_token:
        return None, JSONResponse(
            {
                "ok": False,
                "error": "GitHub token not configured. "
                "Set github_token in config or RELEASEPILOT_GITHUB_TOKEN env var.",
            },
            status_code=400,
        )

    try:
        inspector = GitHubInspector.from_config(
            github_token=github_token,
            github_url=github_url,
        )
        return inspector, None
    except GitHubError as exc:
        return None, JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=400,
        )


@router.post("/validate")
async def api_github_validate(request: Request) -> Response:
    """Validate GitHub connection and token."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    body, body_err = await read_json_body(request)
    if body_err:
        return body_err

    config = request.app.state.app_state.config
    if body:
        for key in ("github_token", "github_url"):
            if key in body:
                config[key] = body[key]

    inspector, err = _get_github_inspector(config)
    if err:
        return err

    from releasepilot.sources.github import GitHubError

    try:
        result = await asyncio.to_thread(inspector._client.validate_token)
        return JSONResponse(
            {
                "ok": True,
                "user": result.get("login", ""),
                "name": result.get("name", ""),
                "message": f"Authenticated as {result.get('login', 'unknown')}",
            }
        )
    except GitHubError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=401 if exc.is_auth_error else 502,
        )


@router.post("/inspect")
async def api_github_inspect(request: Request) -> Response:
    """Inspect a remote GitHub repository."""
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
    owner = body.get("owner", "")
    repo = body.get("repo", "")

    if not owner and body.get("url"):
        from releasepilot.sources.github import parse_github_url

        owner, repo = parse_github_url(body["url"])

    if not owner or not repo:
        return JSONResponse(
            {
                "ok": False,
                "error": "Missing 'owner' and 'repo' fields "
                "(or provide 'url' like 'https://github.com/owner/repo')",
            },
            status_code=400,
        )

    config = request.app.state.app_state.config
    inspector, err = _get_github_inspector(config)
    if err:
        return err

    result = await asyncio.to_thread(inspector.inspect, owner, repo)

    response: dict[str, Any] = {
        "ok": result.is_accessible,
        "is_authenticated": result.is_authenticated,
        "is_accessible": result.is_accessible,
        "default_branch": result.default_branch,
        "diagnostics": list(result.diagnostics),
    }

    if result.repo:
        response["repo"] = {
            "id": result.repo.id,
            "name": result.repo.name,
            "full_name": result.repo.full_name,
            "html_url": result.repo.html_url,
            "visibility": result.repo.visibility,
        }

    if result.branches:
        response["branches"] = [
            {"name": b.name, "commit": b.commit_sha[:8], "protected": b.is_protected}
            for b in result.branches
        ]

    if result.tags:
        response["tags"] = [{"name": t.name, "commit": t.commit_sha[:8]} for t in result.tags]

    if result.error:
        response["error"] = result.error
        response["error_kind"] = result.error_kind

    status = 200 if result.is_accessible else (401 if not result.is_authenticated else 404)
    return JSONResponse(response, status_code=status)


@router.get("/branches/{owner}/{repo}")
async def api_github_branches(owner: str, repo: str, request: Request) -> Response:
    """List branches for a GitHub repository."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    config = request.app.state.app_state.config
    inspector, err = _get_github_inspector(config)
    if err:
        return err

    from releasepilot.sources.github import GitHubError

    try:
        branches = await asyncio.to_thread(inspector._client.list_branches, owner, repo)
        return JSONResponse(
            {
                "ok": True,
                "count": len(branches),
                "branches": [
                    {"name": b.name, "commit": b.commit_sha[:8], "protected": b.is_protected}
                    for b in branches
                ],
            }
        )
    except GitHubError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=502,
        )


@router.get("/tags/{owner}/{repo}")
async def api_github_tags(owner: str, repo: str, request: Request) -> Response:
    """List tags for a GitHub repository."""
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    config = request.app.state.app_state.config
    inspector, err = _get_github_inspector(config)
    if err:
        return err

    from releasepilot.sources.github import GitHubError

    try:
        tags = await asyncio.to_thread(inspector._client.list_tags, owner, repo)
        return JSONResponse(
            {
                "ok": True,
                "count": len(tags),
                "tags": [{"name": t.name, "commit": t.commit_sha[:8]} for t in tags],
            }
        )
    except GitHubError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=502,
        )


# ── Organisation Repository Discovery ────────────────────────────────


@router.post("/org-repos")
async def api_github_org_repos(request: Request) -> Response:
    """List repositories under a GitHub organisation or user account."""
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
    org = body.get("org", "").strip()
    if not org:
        return JSONResponse({"ok": False, "error": "Missing 'org' field"}, status_code=400)

    config = request.app.state.app_state.config
    token = (
        body.get("token", "")
        or config.get("github_token", "")
        or os.environ.get("RELEASEPILOT_GITHUB_TOKEN", "")
    )
    verify_ssl = body.get("verify_ssl", True)

    from releasepilot.sources.github import GitHubClient, GitHubError

    try:
        client = GitHubClient(token=token, verify_ssl=verify_ssl)
        repos = await asyncio.to_thread(client.list_org_repos, org)
        return JSONResponse(
            {
                "ok": True,
                "org": org,
                "count": len(repos),
                "repos": [
                    {
                        "name": r.name,
                        "full_name": r.full_name,
                        "url": r.html_url,
                        "default_branch": r.default_branch,
                        "visibility": r.visibility,
                        "description": r.description,
                    }
                    for r in repos
                ],
            }
        )
    except GitHubError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "error_kind": exc.kind.value},
            status_code=502,
        )
