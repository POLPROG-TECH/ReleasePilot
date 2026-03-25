"""Source collector factory.

Creates the appropriate ``SourceCollector`` instances based on configuration.
This is the single dispatch point for the pipeline — it decides whether to use
local git, remote GitLab, remote GitHub, structured file, or multi-repo collection.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("releasepilot.source_factory")


# ── Repository Source Definition ────────────────────────────────────────────


@dataclass(frozen=True)
class RepoSource:
    """Defines a single repository source for the pipeline.

    This is the normalised internal representation — created from user input
    (URL, local path, config) by ``parse_repo_source()``.
    """

    source_type: str  # "local", "github", "gitlab"
    # Local fields
    repo_path: str = ""
    # Remote fields
    url: str = ""
    owner: str = ""  # GitHub owner or GitLab group path
    repo: str = ""  # Repository name
    project_path: str = ""  # GitLab full project path (group/subgroup/repo)
    # Auth
    token: str = ""
    verify_ssl: bool = True
    # Display
    app_label: str = ""

    @property
    def display_name(self) -> str:
        if self.app_label:
            return self.app_label
        if self.source_type == "local":
            return self.repo_path or "."
        if self.source_type == "github":
            return f"{self.owner}/{self.repo}"
        if self.source_type == "gitlab":
            return self.project_path or f"{self.owner}/{self.repo}"
        return self.url or "unknown"


# ── URL Detection ───────────────────────────────────────────────────────────

_GITHUB_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/.]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

# Patterns that indicate an org/user page — NOT a repository
_GITHUB_ORG_PATTERNS = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?:orgs/[^/]+(?:/.*)?$"  # /orgs/NAME or /orgs/NAME/anything
    r"|[^/]+/?$"  # /NAME (single path segment = user/org page)
    r"|[^/]+/[^/]+/(?:tree|blob|issues|pulls|actions|settings|wiki|releases|tags|branches|commits|compare)/)",  # deep repo links
    re.IGNORECASE,
)

_GITLAB_URL_RE = re.compile(
    r"(?:https?://)?([^/]+)/(.+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def detect_provider(url: str) -> str:
    """Detect the Git provider from a URL.

    Returns "github", "gitlab", or "unknown".
    """
    url_lower = url.lower().strip()
    if "github.com" in url_lower:
        return "github"
    if "gitlab" in url_lower:
        return "gitlab"
    return "unknown"


def parse_repo_source(
    url_or_path: str,
    *,
    provider: str = "",
    token: str = "",
    verify_ssl: bool = True,
    app_label: str = "",
    gitlab_url: str = "",
) -> RepoSource:
    """Parse a repository URL or path into a RepoSource.

    Auto-detects provider from URL if not specified.
    """
    url_or_path = url_or_path.strip()

    # Local path detection (absolute, relative, or .)
    if not url_or_path.startswith(("http://", "https://")) and not provider:
        return RepoSource(
            source_type="local",
            repo_path=url_or_path,
            app_label=app_label,
        )

    if not provider:
        provider = detect_provider(url_or_path)

    if provider == "github":
        match = _GITHUB_URL_RE.match(url_or_path)
        if match:
            owner, repo = match.group(1), match.group(2)
        else:
            # URL didn't match owner/repo pattern — don't guess
            owner, repo = "", ""
            logger.warning("GitHub URL did not match owner/repo pattern: %s", url_or_path)
        return RepoSource(
            source_type="github",
            url=url_or_path,
            owner=owner,
            repo=repo,
            token=token,
            verify_ssl=verify_ssl,
            app_label=app_label or (f"{owner}/{repo}" if owner and repo else url_or_path),
        )

    if provider == "gitlab":
        # Extract project path from URL
        project_path = ""
        if "://" in url_or_path:
            # Full URL — extract path after the domain
            parts = url_or_path.split("://", 1)[1].split("/", 1)
            if len(parts) == 2:
                project_path = parts[1].rstrip("/").removesuffix(".git")
        else:
            project_path = url_or_path.rstrip("/").removesuffix(".git")

        # Split into owner and repo
        path_parts = project_path.rsplit("/", 1)
        owner = path_parts[0] if len(path_parts) > 1 else ""
        repo = path_parts[-1]

        return RepoSource(
            source_type="gitlab",
            url=url_or_path,
            owner=owner,
            repo=repo,
            project_path=project_path,
            token=token,
            verify_ssl=verify_ssl,
            app_label=app_label or project_path,
            # Infer gitlab base URL from the full URL
        )

    # Unknown provider — treat as gitlab-ish remote
    return RepoSource(
        source_type=provider or "unknown",
        url=url_or_path,
        token=token,
        verify_ssl=verify_ssl,
        app_label=app_label or url_or_path,
    )


# ── Collector Factory ───────────────────────────────────────────────────────


def create_collector(
    source: RepoSource,
    *,
    branch: str = "",
    gitlab_base_url: str = "",
) -> object:
    """Create a SourceCollector for the given RepoSource.

    Returns an object implementing the SourceCollector protocol.
    """
    if source.source_type == "local":
        from releasepilot.sources.git import GitSourceCollector

        return GitSourceCollector(source.repo_path or ".")

    if source.source_type == "github":
        from releasepilot.sources.github import GitHubClient
        from releasepilot.sources.github_collector import GitHubSourceCollector

        client = GitHubClient(
            token=source.token,
            verify_ssl=source.verify_ssl,
        )
        return GitHubSourceCollector(
            client=client,
            owner=source.owner,
            repo=source.repo,
            app_label=source.app_label,
            branch=branch,
        )

    if source.source_type == "gitlab":
        from releasepilot.sources.gitlab import GitLabClient
        from releasepilot.sources.gitlab_collector import GitLabSourceCollector

        base_url = gitlab_base_url
        if not base_url and source.url and "://" in source.url:
            # Infer base URL: https://gitlab.example.com/group/repo → https://gitlab.example.com
            parts = source.url.split("://", 1)
            domain = parts[1].split("/", 1)[0]
            base_url = f"{parts[0]}://{domain}"

        if not base_url:
            raise ValueError(
                f"Cannot determine GitLab base URL for source '{source.display_name}'. "
                "Provide gitlab_url in config or use a full HTTPS URL."
            )

        client = GitLabClient(
            base_url=base_url,
            token=source.token,
            verify_ssl=source.verify_ssl,
        )
        # Resolve project ID via API
        project = client.get_project(source.project_path)
        return GitLabSourceCollector(
            client=client,
            project_id=project.id,
            app_label=source.app_label,
            branch=branch,
        )

    raise ValueError(f"Unsupported source type: {source.source_type}")


# ── Source Validation ───────────────────────────────────────────────────────

# URL patterns for strict validation
_GITHUB_URL_VALID = re.compile(
    r"^https?://(?:www\.)?github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?:\.git)?/?$",
    re.IGNORECASE,
)

_GITLAB_URL_VALID = re.compile(
    r"^https?://[^/]+(?:/[A-Za-z0-9._-]+){2,}(?:\.git)?/?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceValidationResult:
    """Result of validating a repository source URL or path."""

    valid: bool
    provider: str  # "github", "gitlab", "local", "unknown"
    source_type: str  # "local", "github", "gitlab"
    display_name: str = ""
    owner: str = ""
    repo: str = ""
    project_path: str = ""
    error: str = ""
    requires_token: bool = False
    url: str = ""
    is_org: bool = False  # True if URL points to an org/group, not a repo
    org_name: str = ""  # Extracted org/group identifier for discovery


def validate_repo_source(
    url_or_path: str,
    *,
    provider: str = "",
    token: str = "",
    app_label: str = "",
) -> SourceValidationResult:
    """Validate a repository URL or local path.

    Checks:
    - URL format validity for GitHub/GitLab
    - Local path existence and git repository detection
    - Provider detection
    - Token requirements

    Returns a structured result — never raises.
    """
    url_or_path = url_or_path.strip()

    if not url_or_path:
        return SourceValidationResult(
            valid=False,
            provider="unknown",
            source_type="unknown",
            error="Repository URL or path is required.",
        )

    # Local path detection
    is_url = url_or_path.startswith(("http://", "https://"))
    if not is_url and not provider:
        return _validate_local_path(url_or_path, app_label=app_label)

    if provider == "local" or (not is_url and provider == ""):
        return _validate_local_path(url_or_path, app_label=app_label)

    # Remote URL validation
    detected_provider = provider or detect_provider(url_or_path)

    if detected_provider == "github":
        return _validate_github_url(url_or_path, token=token, app_label=app_label)
    if detected_provider == "gitlab":
        return _validate_gitlab_url(url_or_path, token=token, app_label=app_label)

    # Unknown provider — try to parse as generic remote
    return SourceValidationResult(
        valid=False,
        provider="unknown",
        source_type="unknown",
        url=url_or_path,
        error=(
            "Cannot detect repository provider from URL. "
            "Supported providers: GitHub (github.com), GitLab. "
            "Ensure the URL is a valid repository link."
        ),
    )


def _validate_local_path(path: str, *, app_label: str = "") -> SourceValidationResult:
    """Validate a local repository path."""
    resolved = Path(path).resolve()
    display = app_label or resolved.name

    if not resolved.is_dir():
        return SourceValidationResult(
            valid=False,
            provider="local",
            source_type="local",
            display_name=display,
            error=f"Directory does not exist: '{path}'",
        )

    git_dir = resolved / ".git"
    if not git_dir.exists():
        return SourceValidationResult(
            valid=False,
            provider="local",
            source_type="local",
            display_name=display,
            error=f"Not a Git repository (no .git directory): '{path}'",
        )

    return SourceValidationResult(
        valid=True,
        provider="local",
        source_type="local",
        display_name=display,
    )


_GITHUB_ORG_NAME_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?:orgs/)?([A-Za-z0-9._-]+)",
    re.IGNORECASE,
)


def _extract_github_org_name(url: str) -> str:
    """Extract the org/user name from a GitHub org-level URL."""
    m = _GITHUB_ORG_NAME_RE.match(url)
    return m.group(1) if m else ""


def _validate_github_url(
    url: str, *, token: str = "", app_label: str = ""
) -> SourceValidationResult:
    """Validate a GitHub repository URL.

    Org/user pages are detected and returned with ``is_org=True``
    so callers can trigger the discovery flow instead of rejecting.
    """
    # Detect org/user pages that are not concrete repositories
    if _GITHUB_ORG_PATTERNS.match(url):
        # Extract org/user name from the URL
        org_name = _extract_github_org_name(url)
        return SourceValidationResult(
            valid=True,
            provider="github",
            source_type="github",
            url=url,
            is_org=True,
            org_name=org_name,
            display_name=app_label or org_name or url,
        )

    if not _GITHUB_URL_VALID.match(url):
        return SourceValidationResult(
            valid=False,
            provider="github",
            source_type="github",
            url=url,
            error=("Invalid GitHub URL format. Expected: https://github.com/<owner>/<repo>"),
        )

    match = _GITHUB_URL_RE.match(url)
    if not match:
        return SourceValidationResult(
            valid=False,
            provider="github",
            source_type="github",
            url=url,
            error="Could not extract owner/repo from GitHub URL.",
        )

    owner, repo_name = match.group(1), match.group(2)
    display = app_label or f"{owner}/{repo_name}"
    needs_token = not token and not os.environ.get("RELEASEPILOT_GITHUB_TOKEN", "")

    return SourceValidationResult(
        valid=True,
        provider="github",
        source_type="github",
        display_name=display,
        owner=owner,
        repo=repo_name,
        url=url,
        requires_token=needs_token,
    )


def _validate_gitlab_url(
    url: str, *, token: str = "", app_label: str = ""
) -> SourceValidationResult:
    """Validate a GitLab repository URL."""
    if not url.startswith(("http://", "https://")):
        return SourceValidationResult(
            valid=False,
            provider="gitlab",
            source_type="gitlab",
            url=url,
            error="GitLab URL must start with http:// or https://",
        )

    # Extract project path from URL
    try:
        parts = url.split("://", 1)[1].split("/", 1)
        if len(parts) < 2 or not parts[1].strip().strip("/"):
            return SourceValidationResult(
                valid=False,
                provider="gitlab",
                source_type="gitlab",
                url=url,
                error=(
                    "Invalid GitLab URL format. Expected: https://<gitlab-host>/<group>/<project>"
                ),
            )
        project_path = parts[1].rstrip("/").removesuffix(".git")
    except (IndexError, ValueError):
        return SourceValidationResult(
            valid=False,
            provider="gitlab",
            source_type="gitlab",
            url=url,
            error="Could not parse GitLab URL.",
        )

    path_parts = project_path.rsplit("/", 1)
    # Single-segment path → group/namespace, not a specific project
    if len(path_parts) == 1 or (len(path_parts) == 2 and not path_parts[0]):
        group_name = project_path.strip("/")
        return SourceValidationResult(
            valid=True,
            provider="gitlab",
            source_type="gitlab",
            url=url,
            is_org=True,
            org_name=group_name,
            display_name=app_label or group_name,
        )

    owner = path_parts[0] if len(path_parts) > 1 else ""
    repo_name = path_parts[-1]
    display = app_label or project_path
    needs_token = not token and not os.environ.get("RELEASEPILOT_GITLAB_TOKEN", "")

    return SourceValidationResult(
        valid=True,
        provider="gitlab",
        source_type="gitlab",
        display_name=display,
        owner=owner,
        repo=repo_name,
        project_path=project_path,
        url=url,
        requires_token=needs_token,
    )


def create_multi_collector(
    sources: list[RepoSource],
    *,
    branch: str = "",
    gitlab_base_url: str = "",
) -> object:
    """Create a MultiRepoCollector from a list of RepoSources.

    Returns a collector implementing the SourceCollector protocol.
    """
    from releasepilot.sources.multi import MultiRepoCollector

    multi = MultiRepoCollector()
    for source in sources:
        collector = create_collector(
            source,
            branch=branch,
            gitlab_base_url=gitlab_base_url,
        )
        multi.add(source.app_label or source.display_name, collector)

    return multi


def create_collector_from_settings(settings: object) -> object:
    """Create the appropriate collector(s) from a Settings object.

    Dispatches based on Settings fields:
    - is_file_source → StructuredFileCollector
    - is_github_source → GitHubSourceCollector
    - is_gitlab_source → GitLabSourceCollector
    - multi_repo_sources → MultiRepoCollector
    - default → GitSourceCollector (local)
    """
    from releasepilot.config.settings import Settings

    s: Settings = settings  # type: ignore[assignment]

    if s.is_file_source:
        from releasepilot.sources.structured import StructuredFileCollector

        return StructuredFileCollector(s.source_file)

    # Multi-repo mode
    if s.multi_repo_sources:
        sources = []
        for src_def in s.multi_repo_sources:
            source = parse_repo_source(
                src_def.get("url", src_def.get("path", "")),
                provider=src_def.get("provider", ""),
                token=src_def.get("token", s.github_token or s.gitlab_token),
                verify_ssl=src_def.get("verify_ssl", True),
                app_label=src_def.get("app_label", src_def.get("name", "")),
                gitlab_url=s.gitlab_url,
            )
            sources.append(source)
        return create_multi_collector(
            sources,
            branch=s.branch,
            gitlab_base_url=s.gitlab_url,
        )

    # GitHub single-repo
    if s.is_github_source:
        from releasepilot.sources.github import GitHubClient
        from releasepilot.sources.github_collector import GitHubSourceCollector

        client = GitHubClient(
            token=s.github_token,
            verify_ssl=s.github_ssl_verify,
        )
        return GitHubSourceCollector(
            client=client,
            owner=s.github_owner,
            repo=s.github_repo,
            app_label=s.app_name or f"{s.github_owner}/{s.github_repo}",
            branch=s.branch,
        )

    # GitLab single-repo
    if s.is_gitlab_source:
        from releasepilot.sources.gitlab import GitLabClient
        from releasepilot.sources.gitlab_collector import GitLabSourceCollector

        client = GitLabClient(
            base_url=s.gitlab_url,
            token=s.gitlab_token,
            verify_ssl=s.gitlab_ssl_verify,
        )
        project = client.get_project(s.gitlab_project)
        return GitLabSourceCollector(
            client=client,
            project_id=project.id,
            app_label=s.app_name or s.gitlab_project,
            branch=s.branch,
        )

    # Default: local git
    from releasepilot.sources.git import GitSourceCollector

    return GitSourceCollector(s.repo_path)
