"""GitLab API client for ReleasePilot.

Provides authenticated access to GitLab repositories for remote branch/tag
resolution, commit collection, and repository inspection.

Key design decisions:
- Token is attached to EVERY request from the first call (no unauthenticated probes)
- Branch/tag names with slashes are properly URL-encoded (e.g. release/2026.04)
- Errors are classified into specific types (auth, permission, network, not-found)
- Responses are cached with TTL to eliminate redundant API calls
- Connection reuse via urllib.request (no external HTTP dependency required)
- SSL context uses centralised ``make_ssl_context()`` for corporate-network
  compatibility (Zscaler, custom CA bundles, macOS keychain)
- Transient server errors (502/503/504) and rate-limits are retried with
  exponential back-off
- Authentication is header-based (``PRIVATE-TOKEN``), not embedded in URLs -
  Python 3.13+ rejects credentials in URLs as invalid
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from releasepilot.shared.network import make_no_verify_ssl_context, make_ssl_context

logger = logging.getLogger("releasepilot.gitlab")

# ── Error Types ─────────────────────────────────────────────────────────────


class GitLabErrorKind(StrEnum):
    """Classifies the root cause of a GitLab API failure."""

    AUTH_FAILED = "auth_failed"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    INVALID_RESPONSE = "invalid_response"
    SSL_ERROR = "ssl_error"


class GitLabError(Exception):
    """Raised when a GitLab API operation fails."""

    def __init__(self, message: str, kind: GitLabErrorKind, status_code: int = 0) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code

    def __str__(self) -> str:
        return f"[{self.kind.value}] {super().__str__()}"

    @property
    def is_auth_error(self) -> bool:
        return self.kind in (GitLabErrorKind.AUTH_FAILED, GitLabErrorKind.PERMISSION_DENIED)

    @property
    def is_retriable(self) -> bool:
        return self.kind in (
            GitLabErrorKind.NETWORK_ERROR,
            GitLabErrorKind.TIMEOUT,
            GitLabErrorKind.RATE_LIMITED,
            GitLabErrorKind.SERVER_ERROR,
        )


# ── Data Models ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GitLabBranch:
    """A branch from the GitLab API."""

    name: str
    commit_sha: str = ""
    commit_date: str = ""
    is_default: bool = False
    is_protected: bool = False


@dataclass(frozen=True)
class GitLabTag:
    """A tag from the GitLab API."""

    name: str
    commit_sha: str = ""
    commit_date: str = ""
    message: str = ""


@dataclass(frozen=True)
class GitLabProject:
    """Minimal project metadata from the GitLab API."""

    id: int
    name: str
    path_with_namespace: str
    default_branch: str = ""
    web_url: str = ""
    visibility: str = ""
    description: str = ""


@dataclass(frozen=True)
class GitLabCommit:
    """A commit from the GitLab API."""

    sha: str
    short_id: str
    title: str
    message: str
    author_name: str
    authored_date: str
    committed_date: str


# ── Cache ───────────────────────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    data: Any
    expires_at: float


class _ResponseCache:
    """Simple in-memory cache with TTL."""

    def __init__(self, default_ttl: float = 60.0) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.data

    def put(self, key: str, data: Any, ttl: float | None = None) -> None:
        self._store[key] = _CacheEntry(
            data=data,
            expires_at=time.monotonic() + (ttl or self._default_ttl),
        )

    def invalidate(self, prefix: str = "") -> None:
        if not prefix:
            self._store.clear()
        else:
            self._store = {k: v for k, v in self._store.items() if not k.startswith(prefix)}


# ── URL Encoding Helper ────────────────────────────────────────────────────


def encode_ref(ref: str) -> str:
    """URL-encode a git ref for use in GitLab API paths.

    GitLab requires refs with slashes to be fully URL-encoded:
    ``release/2026.04`` → ``release%2F2026.04``

    This uses full path encoding (not query encoding) so slashes become %2F.
    """
    return urllib.parse.quote(ref, safe="")


def encode_project_path(path: str) -> str:
    """URL-encode a project path for use in GitLab API paths.

    ``EMEA/GAD/MerchantPortal/UI/additional-reports`` → ``EMEA%2FGAD%2F...``
    """
    return urllib.parse.quote(path, safe="")


# ── Client ──────────────────────────────────────────────────────────────────


class GitLabClient:
    """Authenticated GitLab API v4 client.

    Usage::

        client = GitLabClient(
            base_url="https://gitlab.example.com",
            token="glpat-xxxxxxxxxxxxxxxxxxxx",
        )
        project = client.get_project("group/subgroup/repo")
        branches = client.list_branches(project.id)
        branch = client.get_branch(project.id, "release/2026.04")
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30.0,
        cache_ttl: float = 60.0,
        verify_ssl: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._cache = _ResponseCache(default_ttl=cache_ttl)
        self._verify_ssl = verify_ssl

        if not token:
            raise GitLabError(
                "GitLab token is required. Set RELEASEPILOT_GITLAB_TOKEN or provide via config.",
                kind=GitLabErrorKind.AUTH_FAILED,
            )

    # ── Core Request Method ─────────────────────────────────────────────

    # Transient HTTP status codes worth retrying
    _TRANSIENT_STATUS_CODES = frozenset({429, 502, 503, 504})
    _MAX_RETRIES = 2
    _RETRY_BASE_DELAY = 0.5

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        use_cache: bool = True,
    ) -> Any:
        """Make an authenticated API request.

        The token is attached to EVERY request as ``PRIVATE-TOKEN`` header.
        No unauthenticated fallback is ever attempted.

        Retries up to ``_MAX_RETRIES`` times on transient server errors
        (502/503/504) and rate-limits (429) with exponential back-off.
        Non-transient failures (DNS, SSL, timeout, 4xx) fail immediately.
        """
        url = f"{self._base_url}/api/v4{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        cache_key = f"{method}:{url}"
        if use_cache and method == "GET":
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return cached

        headers = {
            "PRIVATE-TOKEN": self._token,
            "Accept": "application/json",
            "User-Agent": "ReleasePilot/1.0",
        }

        # Build SSL context: use centralised make_ssl_context() for corporate
        # network compatibility, or a no-verify context when explicitly disabled.
        ctx = make_ssl_context() if self._verify_ssl else make_no_verify_ssl_context()

        last_exc: Exception | None = None
        for attempt in range(1 + self._MAX_RETRIES):
            req = urllib.request.Request(url, method=method, headers=headers)

            logger.debug("%s %s (attempt %d)", method, url, attempt + 1)
            start = time.monotonic()

            try:
                with urllib.request.urlopen(req, timeout=self._timeout, context=ctx) as resp:
                    elapsed = time.monotonic() - start
                    body = resp.read()
                    logger.debug(
                        "%s %s → %d (%dms, %d bytes)",
                        method,
                        path,
                        resp.status,
                        round(elapsed * 1000),
                        len(body),
                    )

                    if not body:
                        return None

                    data = json.loads(body)

                    if use_cache and method == "GET":
                        self._cache.put(cache_key, data)

                    return data

            except urllib.error.HTTPError as exc:
                elapsed = time.monotonic() - start
                body_text = ""
                with contextlib.suppress(Exception):
                    body_text = exc.read().decode("utf-8", errors="replace")

                logger.warning(
                    "%s %s → %d (%dms): %s",
                    method,
                    path,
                    exc.code,
                    round(elapsed * 1000),
                    body_text[:200],
                )

                # Retry on transient server errors (not auth/permission/not-found)
                if exc.code in self._TRANSIENT_STATUS_CODES and attempt < self._MAX_RETRIES:
                    wait = self._RETRY_BASE_DELAY * (2**attempt)
                    logger.info(
                        "Transient error (HTTP %d), retrying in %.1fs… (attempt %d/%d)",
                        exc.code,
                        wait,
                        attempt + 1,
                        1 + self._MAX_RETRIES,
                    )
                    time.sleep(wait)
                    last_exc = exc
                    continue

                raise self._classify_http_error(exc.code, body_text, url) from exc

            except urllib.error.URLError as exc:
                reason = str(exc.reason) if exc.reason else str(exc)

                # SSL errors and network errors are not transient - fail immediately
                import ssl as _ssl

                if isinstance(exc.reason, _ssl.SSLError):
                    raise GitLabError(
                        f"SSL error connecting to {self._base_url}: {reason}. "
                        "Check SSL_CERT_FILE or REQUESTS_CA_BUNDLE environment variables, "
                        "or install the 'certifi' package. "
                        "As a last resort, set verify_ssl=False.",
                        kind=GitLabErrorKind.SSL_ERROR,
                    ) from exc

                raise GitLabError(
                    f"Cannot connect to {self._base_url}: {reason}. "
                    "Check the URL, network connectivity, and proxy settings.",
                    kind=GitLabErrorKind.NETWORK_ERROR,
                ) from exc

            except TimeoutError as exc:
                raise GitLabError(
                    f"Request to {url} timed out after {self._timeout}s",
                    kind=GitLabErrorKind.TIMEOUT,
                ) from exc

            except json.JSONDecodeError as exc:
                raise GitLabError(
                    f"Invalid JSON response from {url}",
                    kind=GitLabErrorKind.INVALID_RESPONSE,
                ) from exc

        # Exhausted retries
        if last_exc:
            raise GitLabError(
                f"Request failed after {1 + self._MAX_RETRIES} attempts: {last_exc}",
                kind=GitLabErrorKind.SERVER_ERROR,
            ) from last_exc
        raise GitLabError(
            f"Request to {url} failed after {1 + self._MAX_RETRIES} attempts",
            kind=GitLabErrorKind.SERVER_ERROR,
        )

    def _classify_http_error(
        self,
        status: int,
        body: str,
        url: str,
    ) -> GitLabError:
        """Convert HTTP status codes to specific GitLabError kinds."""
        if status == 401:
            return GitLabError(
                "Authentication failed. The GitLab token is invalid or expired. "
                "Check RELEASEPILOT_GITLAB_TOKEN.",
                kind=GitLabErrorKind.AUTH_FAILED,
                status_code=401,
            )
        if status == 403:
            return GitLabError(
                "Permission denied. The token does not have access to this resource. "
                "Ensure the token has 'read_api' or 'read_repository' scope.",
                kind=GitLabErrorKind.PERMISSION_DENIED,
                status_code=403,
            )
        if status == 404:
            return GitLabError(
                f"Resource not found: {url}. "
                "The project, branch, or tag may not exist, or the token "
                "lacks visibility into this project.",
                kind=GitLabErrorKind.NOT_FOUND,
                status_code=404,
            )
        if status == 429:
            return GitLabError(
                "GitLab API rate limit exceeded. Wait before retrying.",
                kind=GitLabErrorKind.RATE_LIMITED,
                status_code=429,
            )
        if status >= 500:
            return GitLabError(
                f"GitLab server error ({status}). The GitLab instance may be experiencing issues.",
                kind=GitLabErrorKind.SERVER_ERROR,
                status_code=status,
            )
        return GitLabError(
            f"GitLab API request failed with status {status}: {body[:200]}",
            kind=GitLabErrorKind.INVALID_RESPONSE,
            status_code=status,
        )

    # ── High-Level API Methods ──────────────────────────────────────────

    def validate_token(self) -> dict:
        """Validate the token by fetching the current user.

        Should be the FIRST call made to confirm authentication works.
        Raises GitLabError with AUTH_FAILED if the token is invalid.
        """
        return self._request("GET", "/user", use_cache=False)

    def get_project(self, project_path_or_id: str | int) -> GitLabProject:
        """Fetch project metadata.

        Accepts either a numeric ID or a URL-encoded path like
        ``EMEA%2FGAD%2FMerchantPortal%2FUI%2Fadditional-reports``.
        """
        if isinstance(project_path_or_id, int):
            encoded = str(project_path_or_id)
        else:
            encoded = encode_project_path(project_path_or_id)

        data = self._request("GET", f"/projects/{encoded}")
        return GitLabProject(
            id=data["id"],
            name=data.get("name", ""),
            path_with_namespace=data.get("path_with_namespace", ""),
            default_branch=data.get("default_branch", ""),
            web_url=data.get("web_url", ""),
            visibility=data.get("visibility", ""),
            description=data.get("description", ""),
        )

    def list_branches(
        self,
        project_id: int,
        *,
        search: str = "",
        per_page: int = 100,
    ) -> list[GitLabBranch]:
        """List branches for a project."""
        params: dict[str, str] = {"per_page": str(per_page)}
        if search:
            params["search"] = search

        data = self._request("GET", f"/projects/{project_id}/repository/branches", params=params)
        return [
            GitLabBranch(
                name=b["name"],
                commit_sha=b.get("commit", {}).get("id", ""),
                commit_date=b.get("commit", {}).get("committed_date", ""),
                is_default=b.get("default", False),
                is_protected=b.get("protected", False),
            )
            for b in (data or [])
        ]

    def get_branch(self, project_id: int, branch_name: str) -> GitLabBranch:
        """Fetch a single branch by name.

        Branch names containing slashes (e.g. ``release/2026.04``) are
        properly URL-encoded so the GitLab API resolves them correctly.
        """
        encoded = encode_ref(branch_name)
        data = self._request(
            "GET",
            f"/projects/{project_id}/repository/branches/{encoded}",
        )
        return GitLabBranch(
            name=data["name"],
            commit_sha=data.get("commit", {}).get("id", ""),
            commit_date=data.get("commit", {}).get("committed_date", ""),
            is_default=data.get("default", False),
            is_protected=data.get("protected", False),
        )

    def list_tags(
        self,
        project_id: int,
        *,
        search: str = "",
        per_page: int = 100,
        order_by: str = "updated",
    ) -> list[GitLabTag]:
        """List tags for a project."""
        params: dict[str, str] = {
            "per_page": str(per_page),
            "order_by": order_by,
        }
        if search:
            params["search"] = search

        data = self._request("GET", f"/projects/{project_id}/repository/tags", params=params)
        return [
            GitLabTag(
                name=t["name"],
                commit_sha=t.get("commit", {}).get("id", ""),
                commit_date=t.get("commit", {}).get("committed_date", ""),
                message=t.get("message", ""),
            )
            for t in (data or [])
        ]

    def get_tag(self, project_id: int, tag_name: str) -> GitLabTag:
        """Fetch a single tag by name."""
        encoded = encode_ref(tag_name)
        data = self._request(
            "GET",
            f"/projects/{project_id}/repository/tags/{encoded}",
        )
        return GitLabTag(
            name=data["name"],
            commit_sha=data.get("commit", {}).get("id", ""),
            commit_date=data.get("commit", {}).get("committed_date", ""),
            message=data.get("message", ""),
        )

    def list_commits(
        self,
        project_id: int,
        *,
        ref: str = "",
        since: str = "",
        until: str = "",
        per_page: int = 100,
        page: int = 1,
    ) -> list[GitLabCommit]:
        """List commits for a project, optionally filtered by ref and date range."""
        params: dict[str, str] = {
            "per_page": str(per_page),
            "page": str(page),
        }
        if ref:
            params["ref_name"] = ref
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        data = self._request(
            "GET",
            f"/projects/{project_id}/repository/commits",
            params=params,
            use_cache=False,
        )
        return [
            GitLabCommit(
                sha=c["id"],
                short_id=c.get("short_id", c["id"][:8]),
                title=c.get("title", ""),
                message=c.get("message", ""),
                author_name=c.get("author_name", ""),
                authored_date=c.get("authored_date", ""),
                committed_date=c.get("committed_date", ""),
            )
            for c in (data or [])
        ]

    def compare(
        self,
        project_id: int,
        from_ref: str,
        to_ref: str,
    ) -> dict:
        """Compare two refs and return the diff summary."""
        params = {
            "from": from_ref,
            "to": to_ref,
        }
        return self._request(
            "GET",
            f"/projects/{project_id}/repository/compare",
            params=params,
            use_cache=False,
        )

    def invalidate_cache(self, project_id: int | None = None) -> None:
        """Clear cached responses, optionally for a specific project."""
        if project_id is not None:
            self._cache.invalidate(f"GET:{self._base_url}/api/v4/projects/{project_id}")
        else:
            self._cache.invalidate()

    # ── Group / Subgroup Discovery ─────────────────────────────────────

    def list_group_projects(
        self,
        group_path: str,
        *,
        per_page: int = 100,
        max_pages: int = 3,
        include_subgroups: bool = True,
    ) -> list[GitLabProject]:
        """List projects under a GitLab group (or subgroup).

        Uses ``/groups/{id}/projects`` with ``include_subgroups=true``.
        Returns up to *per_page × max_pages* projects, sorted by
        most-recently-active.
        """
        encoded = encode_project_path(group_path)
        projects: list[GitLabProject] = []

        for page in range(1, max_pages + 1):
            params: dict[str, str] = {
                "per_page": str(per_page),
                "page": str(page),
                "order_by": "last_activity_at",
                "sort": "desc",
                "archived": "false",
            }
            if include_subgroups:
                params["include_subgroups"] = "true"

            items = self._request("GET", f"/groups/{encoded}/projects", params=params)
            if not items:
                break
            for item in items:
                projects.append(
                    GitLabProject(
                        id=item["id"],
                        name=item.get("name", ""),
                        path_with_namespace=item.get("path_with_namespace", ""),
                        default_branch=item.get("default_branch", ""),
                        web_url=item.get("web_url", ""),
                        visibility=item.get("visibility", ""),
                        description=item.get("description") or "",
                    )
                )
            if len(items) < per_page:
                break

        return projects
