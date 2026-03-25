"""GitHub API client for ReleasePilot.

Provides access to GitHub repositories for remote branch/tag resolution,
commit collection, and repository inspection.
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

logger = logging.getLogger("releasepilot.github")

# ── Error Types ─────────────────────────────────────────────────────────────


class GitHubErrorKind(StrEnum):
    """Classifies the root cause of a GitHub API failure."""

    AUTH_FAILED = "auth_failed"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    INVALID_RESPONSE = "invalid_response"
    SSL_ERROR = "ssl_error"


class GitHubError(Exception):
    """Raised when a GitHub API operation fails."""

    def __init__(self, message: str, kind: GitHubErrorKind, status_code: int = 0) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code

    def __str__(self) -> str:
        return f"[{self.kind.value}] {super().__str__()}"

    @property
    def is_auth_error(self) -> bool:
        return self.kind in (GitHubErrorKind.AUTH_FAILED, GitHubErrorKind.PERMISSION_DENIED)

    @property
    def is_retriable(self) -> bool:
        return self.kind in (
            GitHubErrorKind.NETWORK_ERROR,
            GitHubErrorKind.TIMEOUT,
            GitHubErrorKind.RATE_LIMITED,
            GitHubErrorKind.SERVER_ERROR,
        )


# ── Data Models ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GitHubBranch:
    """A branch from the GitHub API."""

    name: str
    commit_sha: str = ""
    is_protected: bool = False


@dataclass(frozen=True)
class GitHubTag:
    """A tag from the GitHub API."""

    name: str
    commit_sha: str = ""


@dataclass(frozen=True)
class GitHubRepo:
    """Minimal repository metadata from the GitHub API."""

    id: int
    name: str
    full_name: str
    default_branch: str = ""
    html_url: str = ""
    visibility: str = ""
    description: str = ""


@dataclass(frozen=True)
class GitHubCommit:
    """A commit from the GitHub API."""

    sha: str
    short_sha: str
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


# ── URL Helpers ─────────────────────────────────────────────────────────────


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL.

    Supports formats:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - github.com/owner/repo
    - owner/repo (short form)

    Returns ("", "") if the URL is not a valid GitHub repository reference.
    """
    url = url.strip().rstrip("/")

    # Remove .git suffix
    if url.endswith(".git"):
        url = url[:-4]

    # Handle full URLs
    if "github.com" in url:
        parts = url.split("github.com/", 1)
        if len(parts) == 2:
            segments = parts[1].strip("/").split("/")
            if len(segments) >= 2:
                return segments[0], segments[1]
        return "", ""

    # Handle owner/repo short form
    segments = url.split("/")
    if len(segments) == 2 and all(
        s and s.isidentifier() or s.replace("-", "").replace("_", "").replace(".", "").isalnum()
        for s in segments
    ):
        return segments[0], segments[1]

    return "", ""


# ── Client ──────────────────────────────────────────────────────────────────


class GitHubClient:
    """Authenticated GitHub REST API v3 client.

    Usage::

        client = GitHubClient(
            token="ghp_xxxxxxxxxxxxxxxxxxxx",
        )
        repo = client.get_repo("owner", "repo")
        branches = client.list_branches("owner", "repo")
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.github.com",
        timeout: float = 30.0,
        cache_ttl: float = 60.0,
        verify_ssl: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._cache = _ResponseCache(default_ttl=cache_ttl)
        self._verify_ssl = verify_ssl

    # ── Core Request Method ─────────────────────────────────────────────

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

        The token is attached as ``Authorization: Bearer`` header.
        Retries on transient server errors with exponential back-off.
        """
        url = f"{self._base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        cache_key = f"{method}:{url}"
        if use_cache and method == "GET":
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return cached

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ReleasePilot/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

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

                # Check for rate limiting via 403 + rate-limit headers
                is_rate_limited = exc.code == 403 and (
                    "rate limit" in body_text.lower()
                    or exc.headers.get("x-ratelimit-remaining") == "0"
                )

                if (
                    exc.code in self._TRANSIENT_STATUS_CODES or is_rate_limited
                ) and attempt < self._MAX_RETRIES:
                    wait = self._RETRY_BASE_DELAY * (2**attempt)
                    # Honour Retry-After header if present
                    retry_after = exc.headers.get("retry-after")
                    if retry_after:
                        with contextlib.suppress(ValueError):
                            wait = max(wait, float(retry_after))
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

                import ssl as _ssl

                if isinstance(exc.reason, _ssl.SSLError):
                    raise GitHubError(
                        f"SSL error connecting to {self._base_url}: {reason}. "
                        "Check SSL_CERT_FILE or REQUESTS_CA_BUNDLE environment variables, "
                        "or install the 'certifi' package.",
                        kind=GitHubErrorKind.SSL_ERROR,
                    ) from exc

                raise GitHubError(
                    f"Cannot connect to {self._base_url}: {reason}. "
                    "Check the URL, network connectivity, and proxy settings.",
                    kind=GitHubErrorKind.NETWORK_ERROR,
                ) from exc

            except TimeoutError as exc:
                raise GitHubError(
                    f"Request to {url} timed out after {self._timeout}s",
                    kind=GitHubErrorKind.TIMEOUT,
                ) from exc

            except json.JSONDecodeError as exc:
                raise GitHubError(
                    f"Invalid JSON response from {url}",
                    kind=GitHubErrorKind.INVALID_RESPONSE,
                ) from exc

        # Exhausted retries
        if last_exc:
            raise GitHubError(
                f"Request failed after {1 + self._MAX_RETRIES} attempts: {last_exc}",
                kind=GitHubErrorKind.SERVER_ERROR,
            ) from last_exc
        raise GitHubError(
            f"Request to {url} failed after {1 + self._MAX_RETRIES} attempts",
            kind=GitHubErrorKind.SERVER_ERROR,
        )

    def _classify_http_error(
        self,
        status: int,
        body: str,
        url: str,
    ) -> GitHubError:
        """Convert HTTP status codes to specific GitHubError kinds."""
        if status == 401:
            return GitHubError(
                "Authentication failed. The GitHub token is invalid or expired. "
                "Check RELEASEPILOT_GITHUB_TOKEN.",
                kind=GitHubErrorKind.AUTH_FAILED,
                status_code=401,
            )
        if status == 403:
            if "rate limit" in body.lower():
                return GitHubError(
                    "GitHub API rate limit exceeded. Wait before retrying.",
                    kind=GitHubErrorKind.RATE_LIMITED,
                    status_code=403,
                )
            return GitHubError(
                "Permission denied. The token does not have access to this resource. "
                "Ensure the token has 'repo' scope for private repositories.",
                kind=GitHubErrorKind.PERMISSION_DENIED,
                status_code=403,
            )
        if status == 404:
            return GitHubError(
                f"Resource not found: {url}. "
                "The repository, branch, or tag may not exist, or the token "
                "lacks visibility into this repository.",
                kind=GitHubErrorKind.NOT_FOUND,
                status_code=404,
            )
        if status == 422:
            return GitHubError(
                f"Validation failed: {body[:200]}",
                kind=GitHubErrorKind.INVALID_RESPONSE,
                status_code=422,
            )
        if status >= 500:
            return GitHubError(
                f"GitHub server error ({status}). GitHub may be experiencing issues.",
                kind=GitHubErrorKind.SERVER_ERROR,
                status_code=status,
            )
        return GitHubError(
            f"GitHub API request failed with status {status}: {body[:200]}",
            kind=GitHubErrorKind.INVALID_RESPONSE,
            status_code=status,
        )

    # ── High-Level API Methods ──────────────────────────────────────────

    def validate_token(self) -> dict:
        """Validate the token by fetching the current user.

        Should be the FIRST call made to confirm authentication works.
        Raises GitHubError with AUTH_FAILED if the token is invalid
        or if no token was provided.
        """
        if not self._token:
            raise GitHubError(
                "No GitHub token provided. Anonymous access does not support "
                "token validation. Provide a token via config or environment.",
                kind=GitHubErrorKind.AUTH_FAILED,
            )
        return self._request("GET", "/user", use_cache=False)

    def get_repo(self, owner: str, repo: str) -> GitHubRepo:
        """Fetch repository metadata."""
        data = self._request("GET", f"/repos/{owner}/{repo}")
        return GitHubRepo(
            id=data["id"],
            name=data.get("name", ""),
            full_name=data.get("full_name", ""),
            default_branch=data.get("default_branch", ""),
            html_url=data.get("html_url", ""),
            visibility=data.get("visibility", ""),
            description=data.get("description") or "",
        )

    def list_branches(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 100,
    ) -> list[GitHubBranch]:
        """List branches for a repository."""
        params: dict[str, str] = {"per_page": str(per_page)}
        data = self._request("GET", f"/repos/{owner}/{repo}/branches", params=params)
        return [
            GitHubBranch(
                name=b["name"],
                commit_sha=b.get("commit", {}).get("sha", ""),
                is_protected=b.get("protected", False),
            )
            for b in (data or [])
        ]

    def get_branch(self, owner: str, repo: str, branch_name: str) -> GitHubBranch:
        """Fetch a single branch by name."""
        encoded = urllib.parse.quote(branch_name, safe="")
        data = self._request("GET", f"/repos/{owner}/{repo}/branches/{encoded}")
        return GitHubBranch(
            name=data["name"],
            commit_sha=data.get("commit", {}).get("sha", ""),
            is_protected=data.get("protected", False),
        )

    def list_tags(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 100,
    ) -> list[GitHubTag]:
        """List tags for a repository."""
        params: dict[str, str] = {"per_page": str(per_page)}
        data = self._request("GET", f"/repos/{owner}/{repo}/tags", params=params)
        return [
            GitHubTag(
                name=t["name"],
                commit_sha=t.get("commit", {}).get("sha", ""),
            )
            for t in (data or [])
        ]

    def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        sha: str = "",
        since: str = "",
        until: str = "",
        per_page: int = 100,
        page: int = 1,
    ) -> list[GitHubCommit]:
        """List commits, optionally filtered by branch/ref and date range."""
        params: dict[str, str] = {
            "per_page": str(per_page),
            "page": str(page),
        }
        if sha:
            params["sha"] = sha
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        data = self._request(
            "GET",
            f"/repos/{owner}/{repo}/commits",
            params=params,
            use_cache=False,
        )
        return [
            GitHubCommit(
                sha=c["sha"],
                short_sha=c["sha"][:8],
                title=c.get("commit", {}).get("message", "").split("\n", 1)[0],
                message=c.get("commit", {}).get("message", ""),
                author_name=(
                    c.get("commit", {}).get("author", {}).get("name", "")
                    or c.get("author", {}).get("login", "")
                    if c.get("author")
                    else ""
                ),
                authored_date=c.get("commit", {}).get("author", {}).get("date", ""),
                committed_date=c.get("commit", {}).get("committer", {}).get("date", ""),
            )
            for c in (data or [])
        ]

    def compare(
        self,
        owner: str,
        repo: str,
        base: str,
        head: str,
    ) -> dict:
        """Compare two refs and return the comparison."""
        base_encoded = urllib.parse.quote(base, safe="")
        head_encoded = urllib.parse.quote(head, safe="")
        return self._request(
            "GET",
            f"/repos/{owner}/{repo}/compare/{base_encoded}...{head_encoded}",
            use_cache=False,
        )

    def invalidate_cache(self, owner: str = "", repo: str = "") -> None:
        """Clear cached responses, optionally for a specific repository."""
        if owner and repo:
            self._cache.invalidate(f"GET:{self._base_url}/repos/{owner}/{repo}")
        else:
            self._cache.invalidate()

    # ── Organisation / User Discovery ──────────────────────────────────

    def list_org_repos(
        self,
        org: str,
        *,
        per_page: int = 100,
        max_pages: int = 3,
        repo_type: str = "sources",
    ) -> list[GitHubRepo]:
        """List repositories for a GitHub organisation or user.

        Tries ``/orgs/{org}/repos`` first (works for organisations).
        Falls back to ``/users/{org}/repos`` (works for personal accounts).
        Returns up to *per_page × max_pages* repositories, sorted by
        most-recently-pushed.
        """
        repos: list[GitHubRepo] = []

        for attempt_path in (
            f"/orgs/{org}/repos",
            f"/users/{org}/repos",
        ):
            try:
                for page in range(1, max_pages + 1):
                    params: dict[str, str] = {
                        "per_page": str(per_page),
                        "page": str(page),
                        "sort": "pushed",
                        "direction": "desc",
                    }
                    if attempt_path.startswith("/orgs/"):
                        params["type"] = repo_type

                    items = self._request("GET", attempt_path, params=params, use_cache=True)
                    if not items:
                        break
                    for item in items:
                        repos.append(
                            GitHubRepo(
                                id=item["id"],
                                name=item.get("name", ""),
                                full_name=item.get("full_name", ""),
                                default_branch=item.get("default_branch", ""),
                                html_url=item.get("html_url", ""),
                                visibility=item.get("visibility", ""),
                                description=item.get("description") or "",
                            )
                        )
                    if len(items) < per_page:
                        break
                return repos  # success — return immediately
            except GitHubError as exc:
                if exc.kind == GitHubErrorKind.NOT_FOUND:
                    continue  # try next endpoint
                raise  # re-raise auth/rate-limit/other errors

        return repos
