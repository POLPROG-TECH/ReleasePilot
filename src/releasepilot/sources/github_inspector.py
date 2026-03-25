"""Remote GitHub repository inspector.

Provides authenticated remote repository inspection analogous to the local
``inspector.py`` — but works over the GitHub API instead of local git commands.

Authentication is applied from the FIRST request. There are no unauthenticated
probes. Every lookup uses the same authenticated session.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from releasepilot.sources.github import (
    GitHubBranch,
    GitHubClient,
    GitHubError,
    GitHubErrorKind,
    GitHubRepo,
    GitHubTag,
)

logger = logging.getLogger("releasepilot.github_inspector")


# ── Data Models ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GitHubRepoInspection:
    """Result of inspecting a remote GitHub repository."""

    repo: GitHubRepo | None = None
    branches: tuple[GitHubBranch, ...] = ()
    tags: tuple[GitHubTag, ...] = ()
    default_branch: str = ""
    is_accessible: bool = False
    is_authenticated: bool = False
    error: str = ""
    error_kind: str = ""
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class BranchLookupResult:
    """Result of looking up a specific branch."""

    found: bool = False
    branch: GitHubBranch | None = None
    error: str = ""
    error_kind: str = ""


@dataclass(frozen=True)
class TagLookupResult:
    """Result of looking up a specific tag."""

    found: bool = False
    tag: GitHubTag | None = None
    error: str = ""
    error_kind: str = ""


# ── Inspector ───────────────────────────────────────────────────────────────


class GitHubInspector:
    """Inspects remote GitHub repositories with auth-first flow.

    Flow:
    1. Validate token (``/user``)
    2. Fetch repository metadata
    3. List branches & tags
    4. Return structured inspection result

    All steps use the authenticated client. If auth fails at step 1,
    we stop immediately and report the specific error.

    Usage::

        inspector = GitHubInspector.from_env()
        result = inspector.inspect("owner", "repo")
        branch = inspector.lookup_branch("owner", "repo", "main")
    """

    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> GitHubInspector:
        """Create an inspector from environment variables.

        Reads:
        - ``RELEASEPILOT_GITHUB_TOKEN`` — Personal access token or fine-grained token
        - ``RELEASEPILOT_GITHUB_URL`` — API URL (defaults to https://api.github.com)
        """
        token = os.environ.get("RELEASEPILOT_GITHUB_TOKEN", "")
        base_url = os.environ.get("RELEASEPILOT_GITHUB_URL", "https://api.github.com")

        if not token:
            raise GitHubError(
                "RELEASEPILOT_GITHUB_TOKEN is not set. Provide a GitHub personal access token.",
                kind=GitHubErrorKind.AUTH_FAILED,
            )

        client = GitHubClient(token=token, base_url=base_url)
        return cls(client)

    @classmethod
    def from_config(
        cls,
        github_token: str,
        *,
        github_url: str = "https://api.github.com",
        verify_ssl: bool = True,
        cache_ttl: float = 60.0,
    ) -> GitHubInspector:
        """Create an inspector from explicit config values."""
        client = GitHubClient(
            token=github_token,
            base_url=github_url,
            verify_ssl=verify_ssl,
            cache_ttl=cache_ttl,
        )
        return cls(client)

    # ── Main Inspection Flow ────────────────────────────────────────────

    def inspect(self, owner: str, repo: str) -> GitHubRepoInspection:
        """Perform a full inspection of a remote GitHub repository.

        Never raises — all errors are captured in the result.
        """
        diagnostics: list[str] = []

        # Step 1: Validate authentication
        try:
            user_info = self._client.validate_token()
            username = user_info.get("login", "unknown")
            diagnostics.append(f"Authenticated as: {username}")
            logger.info("Authenticated to GitHub as %s", username)
        except GitHubError as exc:
            logger.error("GitHub authentication failed: %s", exc)
            return GitHubRepoInspection(
                is_accessible=False,
                is_authenticated=False,
                error=str(exc),
                error_kind=exc.kind.value,
                diagnostics=(
                    f"Authentication failed: {exc}",
                    "Check that RELEASEPILOT_GITHUB_TOKEN is valid and not expired.",
                ),
            )

        # Step 2: Fetch repository metadata
        try:
            repo_info = self._client.get_repo(owner, repo)
            diagnostics.append(f"Repository: {repo_info.full_name}")
            diagnostics.append(f"Default branch: {repo_info.default_branch}")
            diagnostics.append(f"Visibility: {repo_info.visibility}")
            logger.info(
                "Found repository %s (id=%d, default_branch=%s)",
                repo_info.full_name,
                repo_info.id,
                repo_info.default_branch,
            )
        except GitHubError as exc:
            logger.error("Failed to fetch repository %s/%s: %s", owner, repo, exc)
            return GitHubRepoInspection(
                is_accessible=False,
                is_authenticated=True,
                error=str(exc),
                error_kind=exc.kind.value,
                diagnostics=(
                    f"Cannot access repository: {owner}/{repo}",
                    f"Error: {exc}",
                    "Ensure the token has access to this repository.",
                ),
            )

        # Step 3: List branches
        branches: tuple[GitHubBranch, ...] = ()
        try:
            branches = tuple(self._client.list_branches(owner, repo))
            diagnostics.append(f"Branches: {len(branches)} found")
            logger.debug("Listed %d branches for %s/%s", len(branches), owner, repo)
        except GitHubError as exc:
            diagnostics.append(f"Warning: Could not list branches: {exc}")
            logger.warning("Failed to list branches for %s/%s: %s", owner, repo, exc)

        # Step 4: List tags
        tags: tuple[GitHubTag, ...] = ()
        try:
            tags = tuple(self._client.list_tags(owner, repo))
            diagnostics.append(f"Tags: {len(tags)} found")
            logger.debug("Listed %d tags for %s/%s", len(tags), owner, repo)
        except GitHubError as exc:
            diagnostics.append(f"Warning: Could not list tags: {exc}")
            logger.warning("Failed to list tags for %s/%s: %s", owner, repo, exc)

        return GitHubRepoInspection(
            repo=repo_info,
            branches=branches,
            tags=tags,
            default_branch=repo_info.default_branch,
            is_accessible=True,
            is_authenticated=True,
            diagnostics=tuple(diagnostics),
        )

    # ── Targeted Lookups ────────────────────────────────────────────────

    def lookup_branch(
        self,
        owner: str,
        repo: str,
        branch_name: str,
    ) -> BranchLookupResult:
        """Look up a specific branch by exact name."""
        try:
            branch = self._client.get_branch(owner, repo, branch_name)
            return BranchLookupResult(found=True, branch=branch)
        except GitHubError as exc:
            if exc.kind == GitHubErrorKind.NOT_FOUND:
                return BranchLookupResult(
                    found=False,
                    error=f"Branch '{branch_name}' does not exist in {owner}/{repo}.",
                    error_kind=exc.kind.value,
                )
            return BranchLookupResult(
                found=False,
                error=str(exc),
                error_kind=exc.kind.value,
            )

    def lookup_tag(
        self,
        owner: str,
        repo: str,
        tag_name: str,
    ) -> TagLookupResult:
        """Look up a specific tag by name.

        GitHub's tag API is list-based, so we search through the list.
        """
        try:
            tags = self._client.list_tags(owner, repo)
            for t in tags:
                if t.name == tag_name:
                    return TagLookupResult(found=True, tag=t)
            return TagLookupResult(
                found=False,
                error=f"Tag '{tag_name}' does not exist in {owner}/{repo}.",
                error_kind=GitHubErrorKind.NOT_FOUND.value,
            )
        except GitHubError as exc:
            return TagLookupResult(
                found=False,
                error=str(exc),
                error_kind=exc.kind.value,
            )

    def check_branch_exists(self, owner: str, repo: str, branch_name: str) -> bool:
        """Quick check if a branch exists. Returns True/False only."""
        return self.lookup_branch(owner, repo, branch_name).found

    def check_tag_exists(self, owner: str, repo: str, tag_name: str) -> bool:
        """Quick check if a tag exists. Returns True/False only."""
        return self.lookup_tag(owner, repo, tag_name).found
