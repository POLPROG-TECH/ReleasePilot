"""Configuration system for ReleasePilot.

Supports CLI options with sensible defaults.
Configuration is a frozen dataclass — immutable once constructed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from releasepilot.domain.enums import Audience, ChangeCategory, OutputFormat

# Categories hidden from user-facing notes by default
_DEFAULT_INTERNAL_CATEGORIES: frozenset[ChangeCategory] = frozenset(
    {
        ChangeCategory.REFACTOR,
        ChangeCategory.INFRASTRUCTURE,
    }
)

# Patterns that indicate noise commits
_DEFAULT_NOISE_PATTERNS: tuple[str, ...] = (
    r"^Merge (branch|pull request|remote)",
    r"^Revert \"Revert",
    r"^wip\b",
    r"^WIP\b",
    r"^fixup!",
    r"^squash!",
    r"^chore\(deps\):",
    r"^bump version",
    r"^auto-merge",
)


@dataclass(frozen=True)
class FilterConfig:
    """Controls which changes are filtered out."""

    noise_patterns: tuple[str, ...] = _DEFAULT_NOISE_PATTERNS
    exclude_categories: frozenset[ChangeCategory] = frozenset()
    include_categories: frozenset[ChangeCategory] | None = None
    min_importance: str = "noise"


@dataclass(frozen=True)
class RenderConfig:
    """Controls how release notes are rendered."""

    show_authors: bool = False
    show_commit_hashes: bool = False
    show_pr_links: bool = True
    show_scope: bool = True
    group_by_scope: bool = False
    max_items_per_group: int = 0  # 0 = unlimited
    language: str = "en"  # Output language code for label translation
    accent_color: str = "#FB6400"  # Accent / border color for PDF & DOCX


@dataclass(frozen=True)
class Settings:
    """Top-level configuration for a ReleasePilot run."""

    # Source selection
    repo_path: str = "."
    from_ref: str = ""
    to_ref: str = "HEAD"
    source_file: str = ""
    branch: str = ""
    since_date: str = ""  # ISO date string for date-range based collection

    # Output
    audience: Audience = Audience.CHANGELOG
    output_format: OutputFormat = OutputFormat.MARKDOWN
    output_file: str = ""

    # Release metadata
    version: str = ""
    title: str = ""
    app_name: str = ""  # Application/product name (e.g. "Loudly")
    language: str = "en"  # Output language code (e.g. "pl", "de")

    # Filtering
    filter: FilterConfig = field(default_factory=FilterConfig)

    # Rendering
    render: RenderConfig = field(default_factory=RenderConfig)

    # Audience-specific category exclusions
    internal_categories: frozenset[ChangeCategory] = _DEFAULT_INTERNAL_CATEGORIES

    # GitLab remote repository settings
    gitlab_url: str = ""
    gitlab_token: str = ""
    gitlab_project: str = ""
    gitlab_ssl_verify: bool = True

    # GitHub remote repository settings
    github_token: str = ""
    github_owner: str = ""
    github_repo: str = ""
    github_url: str = "https://api.github.com"
    github_ssl_verify: bool = True

    # Multi-repository sources (list of dicts with url/path, provider, token, app_label)
    multi_repo_sources: tuple[dict, ...] = ()

    @property
    def is_file_source(self) -> bool:
        return bool(self.source_file)

    @property
    def is_date_range(self) -> bool:
        return bool(self.since_date)

    @property
    def is_gitlab_source(self) -> bool:
        """True when configured for remote GitLab repository analysis."""
        return bool(self.gitlab_url and self.gitlab_project)

    @property
    def is_github_source(self) -> bool:
        """True when configured for remote GitHub repository analysis."""
        return bool(self.github_owner and self.github_repo)

    @property
    def is_remote_source(self) -> bool:
        """True when configured for any remote repository source."""
        return self.is_gitlab_source or self.is_github_source

    @property
    def is_multi_repo(self) -> bool:
        """True when configured for multi-repository mode."""
        return bool(self.multi_repo_sources)
