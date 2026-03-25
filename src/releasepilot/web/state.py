"""Runtime state management for the ReleasePilot web application."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class AnalysisPhase(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnalysisProgress:
    """Tracks the current state of a generation or dashboard build."""

    phase: AnalysisPhase = AnalysisPhase.IDLE
    stage: str = ""
    detail: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "stage": self.stage,
            "detail": self.detail,
            "error": self.error,
        }


# ── Wizard State ────────────────────────────────────────────────────────────


class WizardStep(StrEnum):
    """Steps in the repository wizard flow."""

    SOURCE_TYPE = "source_type"
    REPOSITORIES = "repositories"
    SCOPE = "scope"
    AUDIENCE = "audience"
    FORMAT = "format"
    REVIEW = "review"
    GENERATING = "generating"
    COMPLETE = "complete"


@dataclass
class WizardRepository:
    """A single repository entry in the wizard.

    Tracks all metadata needed for multi-repo generation.
    """

    id: str = ""
    source_type: str = ""  # "local", "github", "gitlab"
    url: str = ""  # Remote URL or local path
    owner: str = ""
    repo: str = ""
    project_path: str = ""  # GitLab full path
    app_label: str = ""  # Display name / application label
    token: str = ""
    verify_ssl: bool = True
    validated: bool = False
    accessible: bool = False
    error: str = ""
    default_branch: str = ""
    branches: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise for API responses (tokens masked)."""
        return {
            "id": self.id,
            "source_type": self.source_type,
            "url": self.url,
            "owner": self.owner,
            "repo": self.repo,
            "project_path": self.project_path,
            "app_label": self.app_label,
            "token_set": bool(self.token),
            "verify_ssl": self.verify_ssl,
            "validated": self.validated,
            "accessible": self.accessible,
            "error": self.error,
            "default_branch": self.default_branch,
            "branches": self.branches,
            "tags": self.tags,
        }

    def to_source_dict(self) -> dict:
        """Convert to the dict format expected by ``multi_repo_sources``."""
        result: dict = {
            "app_label": self.app_label or self.display_name,
        }
        if self.source_type == "local":
            result["path"] = self.url
            result["provider"] = "local"
        elif self.source_type == "github":
            result["url"] = self.url
            result["provider"] = "github"
            if self.token:
                result["token"] = self.token
            result["verify_ssl"] = self.verify_ssl
        elif self.source_type == "gitlab":
            result["url"] = self.url
            result["provider"] = "gitlab"
            if self.token:
                result["token"] = self.token
            result["verify_ssl"] = self.verify_ssl
        return result

    @property
    def display_name(self) -> str:
        if self.app_label:
            return self.app_label
        if self.source_type == "github" and self.owner and self.repo:
            return f"{self.owner}/{self.repo}"
        if self.source_type == "gitlab" and self.project_path:
            return self.project_path
        return self.url or "unknown"

    @property
    def requires_token(self) -> bool:
        """True if this remote repo needs a token but none is set.

        GitHub public repos that were confirmed accessible during inspection
        do not require a token.  GitLab always requires authentication.
        """
        if self.source_type == "github":
            return not bool(self.token) and not self.accessible
        if self.source_type == "gitlab":
            return not bool(self.token)
        return False


class WizardState:
    """Manages the state of a multi-step repository wizard session.

    Each wizard session tracks:
    - source type (local / remote)
    - repository entries (one or many)
    - shared release range/scope
    - generation options (audience, format, language)
    """

    # Maximum repositories per wizard session
    MAX_REPOSITORIES = 20

    def __init__(self) -> None:
        self.session_id: str = str(uuid.uuid4())
        self.created_at: float = time.time()
        self.step: WizardStep = WizardStep.SOURCE_TYPE
        self.source_type: str = ""  # "local" or "remote"
        self.repositories: list[WizardRepository] = []

        # Shared release range / scope
        self.from_ref: str = ""
        self.to_ref: str = "HEAD"
        self.since_date: str = ""
        self.branch: str = ""

        # Generation options
        self.audience: str = "changelog"
        self.output_format: str = "markdown"
        self.language: str = "en"
        self.app_name: str = ""
        self.version: str = ""
        self.title: str = ""

    def add_repository(self, repo: WizardRepository) -> str | None:
        """Add a repository to the wizard. Returns error message or None."""
        if len(self.repositories) >= self.MAX_REPOSITORIES:
            return f"Maximum of {self.MAX_REPOSITORIES} repositories allowed."

        # Check for duplicate URLs/paths
        for existing in self.repositories:
            if existing.url == repo.url and existing.source_type == repo.source_type:
                return f"Repository already added: {repo.display_name}"

        if not repo.id:
            repo.id = str(uuid.uuid4())
        self.repositories.append(repo)
        return None

    def remove_repository(self, repo_id: str) -> bool:
        """Remove a repository by its ID. Returns True if found and removed."""
        for i, repo in enumerate(self.repositories):
            if repo.id == repo_id:
                self.repositories.pop(i)
                return True
        return False

    def get_repository(self, repo_id: str) -> WizardRepository | None:
        """Get a repository by its ID."""
        for repo in self.repositories:
            if repo.id == repo_id:
                return repo
        return None

    def to_dict(self) -> dict:
        """Serialise the full wizard state for API responses."""
        return {
            "session_id": self.session_id,
            "step": self.step.value,
            "source_type": self.source_type,
            "repositories": [r.to_dict() for r in self.repositories],
            "release_range": {
                "from_ref": self.from_ref,
                "to_ref": self.to_ref,
                "since_date": self.since_date,
                "branch": self.branch,
            },
            "options": {
                "audience": self.audience,
                "output_format": self.output_format,
                "language": self.language,
                "app_name": self.app_name,
                "version": self.version,
                "title": self.title,
            },
            "repository_count": len(self.repositories),
        }

    def to_generation_config(self) -> dict:
        """Build a config dict suitable for ``_build_settings_from_config()``."""
        config: dict = {
            "from_ref": self.from_ref,
            "to_ref": self.to_ref,
            "since_date": self.since_date,
            "branch": self.branch,
            "audience": self.audience,
            "output_format": self.output_format,
            "language": self.language,
            "app_name": self.app_name,
            "version": self.version,
            "title": self.title,
        }

        if len(self.repositories) == 1:
            repo = self.repositories[0]
            if repo.source_type == "local":
                config["repo_path"] = repo.url
            elif repo.source_type == "github":
                config["github_owner"] = repo.owner
                config["github_repo"] = repo.repo
                config["github_token"] = repo.token
                config["github_url"] = "https://api.github.com"
                config["github_ssl_verify"] = repo.verify_ssl
            elif repo.source_type == "gitlab":
                # Infer base URL from the full URL
                if "://" in repo.url:
                    parts = repo.url.split("://", 1)
                    domain = parts[1].split("/", 1)[0]
                    config["gitlab_url"] = f"{parts[0]}://{domain}"
                config["gitlab_token"] = repo.token
                config["gitlab_project"] = repo.project_path
                config["gitlab_ssl_verify"] = repo.verify_ssl
        else:
            # Multi-repo: build source list
            config["multi_repo_sources"] = [r.to_source_dict() for r in self.repositories]
            # For remote repos, pass tokens at the top level as fallback
            for repo in self.repositories:
                if repo.source_type == "github" and repo.token:
                    config.setdefault("github_token", repo.token)
                elif repo.source_type == "gitlab" and repo.token:
                    config.setdefault("gitlab_token", repo.token)
                    if "://" in repo.url:
                        parts = repo.url.split("://", 1)
                        domain = parts[1].split("/", 1)[0]
                        config.setdefault("gitlab_url", f"{parts[0]}://{domain}")

        return config

    def reset(self) -> None:
        """Reset the wizard to initial state."""
        self.session_id = str(uuid.uuid4())
        self.created_at = time.time()
        self.step = WizardStep.SOURCE_TYPE
        self.source_type = ""
        self.repositories = []
        self.from_ref = ""
        self.to_ref = "HEAD"
        self.since_date = ""
        self.branch = ""
        self.audience = "changelog"
        self.output_format = "markdown"
        self.language = "en"
        self.app_name = ""
        self.version = ""
        self.title = ""


class AppState:
    """Shared mutable state for the web application."""

    def __init__(self, config: dict | None = None) -> None:
        self.config: dict = dict(config) if config else {}
        self.analysis_progress = AnalysisProgress()
        self.analysis_lock = asyncio.Lock()
        self.last_result: dict | None = None
        self.last_dashboard_html: str | None = None
        self.wizard = WizardState()
        self._sse_subscribers: list[asyncio.Queue] = []
        # limit max subscribers to prevent memory leak
        self._max_subscribers = 100

    def subscribe(self) -> asyncio.Queue:
        """Create a new SSE subscriber queue."""
        # prune stale subscribers before adding new ones
        self._prune_full_queues()
        if len(self._sse_subscribers) >= self._max_subscribers:
            # Evict oldest subscriber
            self._sse_subscribers.pop(0)
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._sse_subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove an SSE subscriber queue."""
        with contextlib.suppress(ValueError):
            self._sse_subscribers.remove(q)

    def _prune_full_queues(self) -> None:
        """Remove subscriber queues that are full (likely disconnected clients)."""
        self._sse_subscribers = [q for q in self._sse_subscribers if not q.full()]

    async def broadcast(self, event_type: str, data: dict) -> None:
        """Push an event to all SSE subscribers."""
        for q in list(self._sse_subscribers):
            try:
                q.put_nowait({"event": event_type, "data": data})
            except asyncio.QueueFull:
                # remove unresponsive subscribers
                self.unsubscribe(q)
