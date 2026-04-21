"""Remote GitLab repository inspector.

Provides authenticated remote repository inspection analogous to the local
``inspector.py`` - but works over the GitLab API instead of local git commands.

Authentication is applied from the FIRST request. There are no unauthenticated
probes. Every lookup uses the same authenticated session.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from releasepilot.sources.gitlab import (
    GitLabBranch,
    GitLabClient,
    GitLabError,
    GitLabErrorKind,
    GitLabProject,
    GitLabTag,
)

logger = logging.getLogger("releasepilot.gitlab_inspector")


# ── Data Models ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GitLabRepoInspection:
    """Result of inspecting a remote GitLab repository."""

    project: GitLabProject | None = None
    branches: tuple[GitLabBranch, ...] = ()
    tags: tuple[GitLabTag, ...] = ()
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
    branch: GitLabBranch | None = None
    error: str = ""
    error_kind: str = ""


@dataclass(frozen=True)
class TagLookupResult:
    """Result of looking up a specific tag."""

    found: bool = False
    tag: GitLabTag | None = None
    error: str = ""
    error_kind: str = ""


# ── Inspector ───────────────────────────────────────────────────────────────


class GitLabInspector:
    """Inspects remote GitLab repositories with auth-first flow.

    Flow:
    1. Validate token (``/user``)
    2. Fetch project metadata
    3. List branches & tags
    4. Return structured inspection result

    All steps use the authenticated client. If auth fails at step 1,
    we stop immediately and report the specific error.

    Usage::

        inspector = GitLabInspector.from_env()
        result = inspector.inspect("EMEA/GAD/MerchantPortal/UI/additional-reports")
        branch = inspector.lookup_branch(result.project.id, "release/2026.04")
    """

    def __init__(self, client: GitLabClient) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> GitLabInspector:
        """Create an inspector from environment variables.

        Reads:
        - ``RELEASEPILOT_GITLAB_URL`` - GitLab instance URL
        - ``RELEASEPILOT_GITLAB_TOKEN`` - Private token or personal access token
        - ``RELEASEPILOT_GITLAB_SSL_VERIFY`` - Set to "0" or "false" to skip SSL
        """
        base_url = os.environ.get("RELEASEPILOT_GITLAB_URL", "")
        token = os.environ.get("RELEASEPILOT_GITLAB_TOKEN", "")
        verify_ssl = os.environ.get(
            "RELEASEPILOT_GITLAB_SSL_VERIFY",
            "1",
        ).lower() not in ("0", "false", "no")

        if not base_url:
            raise GitLabError(
                "RELEASEPILOT_GITLAB_URL is not set. "
                "Provide the GitLab instance URL (e.g. https://gitlab.example.com).",
                kind=GitLabErrorKind.AUTH_FAILED,
            )

        client = GitLabClient(
            base_url=base_url,
            token=token,
            verify_ssl=verify_ssl,
        )
        return cls(client)

    @classmethod
    def from_config(
        cls,
        gitlab_url: str,
        gitlab_token: str,
        *,
        verify_ssl: bool = True,
        cache_ttl: float = 60.0,
    ) -> GitLabInspector:
        """Create an inspector from explicit config values."""
        client = GitLabClient(
            base_url=gitlab_url,
            token=gitlab_token,
            verify_ssl=verify_ssl,
            cache_ttl=cache_ttl,
        )
        return cls(client)

    # ── Main Inspection Flow ────────────────────────────────────────────

    def inspect(self, project_path: str) -> GitLabRepoInspection:
        """Perform a full inspection of a remote GitLab project.

        This is the primary entry point. It:
        1. Validates the token
        2. Fetches project metadata
        3. Lists branches and tags
        4. Returns a structured result

        Never raises - all errors are captured in the result.
        """
        diagnostics: list[str] = []

        # Step 1: Validate authentication
        try:
            user_info = self._client.validate_token()
            username = user_info.get("username", "unknown")
            diagnostics.append(f"Authenticated as: {username}")
            logger.info("Authenticated to GitLab as %s", username)
        except GitLabError as exc:
            logger.error("GitLab authentication failed: %s", exc)
            return GitLabRepoInspection(
                is_accessible=False,
                is_authenticated=False,
                error=str(exc),
                error_kind=exc.kind.value,
                diagnostics=(
                    f"Authentication failed: {exc}",
                    "Check that RELEASEPILOT_GITLAB_TOKEN is valid and not expired.",
                ),
            )

        # Step 2: Fetch project metadata
        try:
            project = self._client.get_project(project_path)
            diagnostics.append(f"Project: {project.path_with_namespace}")
            diagnostics.append(f"Default branch: {project.default_branch}")
            diagnostics.append(f"Visibility: {project.visibility}")
            logger.info(
                "Found project %s (id=%d, default_branch=%s)",
                project.path_with_namespace,
                project.id,
                project.default_branch,
            )
        except GitLabError as exc:
            logger.error("Failed to fetch project %s: %s", project_path, exc)
            return GitLabRepoInspection(
                is_accessible=False,
                is_authenticated=True,
                error=str(exc),
                error_kind=exc.kind.value,
                diagnostics=(
                    f"Cannot access project: {project_path}",
                    f"Error: {exc}",
                    "Ensure the token has read access to this project.",
                ),
            )

        # Step 3: List branches
        branches: tuple[GitLabBranch, ...] = ()
        try:
            branches = tuple(self._client.list_branches(project.id))
            diagnostics.append(f"Branches: {len(branches)} found")
            logger.debug("Listed %d branches for project %d", len(branches), project.id)
        except GitLabError as exc:
            diagnostics.append(f"Warning: Could not list branches: {exc}")
            logger.warning("Failed to list branches for project %d: %s", project.id, exc)

        # Step 4: List tags
        tags: tuple[GitLabTag, ...] = ()
        try:
            tags = tuple(self._client.list_tags(project.id))
            diagnostics.append(f"Tags: {len(tags)} found")
            logger.debug("Listed %d tags for project %d", len(tags), project.id)
        except GitLabError as exc:
            diagnostics.append(f"Warning: Could not list tags: {exc}")
            logger.warning("Failed to list tags for project %d: %s", project.id, exc)

        return GitLabRepoInspection(
            project=project,
            branches=branches,
            tags=tags,
            default_branch=project.default_branch,
            is_accessible=True,
            is_authenticated=True,
            diagnostics=tuple(diagnostics),
        )

    # ── Targeted Lookups ────────────────────────────────────────────────

    def lookup_branch(
        self,
        project_id: int,
        branch_name: str,
    ) -> BranchLookupResult:
        """Look up a specific branch by exact name.

        Handles branch names with slashes correctly (e.g. ``release/2026.04``).
        Returns a structured result that clearly distinguishes:
        - branch found
        - branch not found
        - auth error
        - network error
        """
        try:
            branch = self._client.get_branch(project_id, branch_name)
            return BranchLookupResult(found=True, branch=branch)
        except GitLabError as exc:
            if exc.kind == GitLabErrorKind.NOT_FOUND:
                return BranchLookupResult(
                    found=False,
                    error=f"Branch '{branch_name}' does not exist in project {project_id}.",
                    error_kind=exc.kind.value,
                )
            return BranchLookupResult(
                found=False,
                error=str(exc),
                error_kind=exc.kind.value,
            )

    def lookup_tag(
        self,
        project_id: int,
        tag_name: str,
    ) -> TagLookupResult:
        """Look up a specific tag by exact name."""
        try:
            tag = self._client.get_tag(project_id, tag_name)
            return TagLookupResult(found=True, tag=tag)
        except GitLabError as exc:
            if exc.kind == GitLabErrorKind.NOT_FOUND:
                return TagLookupResult(
                    found=False,
                    error=f"Tag '{tag_name}' does not exist in project {project_id}.",
                    error_kind=exc.kind.value,
                )
            return TagLookupResult(
                found=False,
                error=str(exc),
                error_kind=exc.kind.value,
            )

    def check_branch_exists(self, project_id: int, branch_name: str) -> bool:
        """Quick check if a branch exists. Returns True/False only."""
        result = self.lookup_branch(project_id, branch_name)
        return result.found

    def check_tag_exists(self, project_id: int, tag_name: str) -> bool:
        """Quick check if a tag exists. Returns True/False only."""
        result = self.lookup_tag(project_id, tag_name)
        return result.found
