"""Dashboard data schema - frozen dataclasses for the ReleasePilot HTML dashboard."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChangeEntry:
    """A single change item for the dashboard."""

    hash: str
    title: str
    category: str
    category_emoji: str
    scope: str
    authors: tuple[str, ...]
    date: str
    importance: str
    breaking: bool
    pr_number: int | None = None
    source: str = "git"


@dataclass(frozen=True)
class ChangeGroupData:
    """A group of changes under one category."""

    category: str
    emoji: str
    count: int
    items: tuple[ChangeEntry, ...]


@dataclass(frozen=True)
class CategoryDistribution:
    """Distribution of changes across categories."""

    category: str
    emoji: str
    count: int
    percentage: float


@dataclass(frozen=True)
class PipelineStageStats:
    """Stats for a single pipeline stage."""

    stage: str
    input_count: int
    output_count: int

    @property
    def removed_count(self) -> int:
        return max(0, self.input_count - self.output_count)

    @property
    def retention_percent(self) -> float:
        if self.input_count == 0:
            return 100.0
        return min(100.0, max(0.0, round(self.output_count / self.input_count * 100, 1)))


@dataclass(frozen=True)
class ArtifactPreview:
    """Preview of a generated artifact."""

    audience: str
    format: str
    content: str
    size_bytes: int


@dataclass(frozen=True)
class DashboardData:
    """Complete data for the ReleasePilot dashboard.

    This frozen dataclass is the single source of truth serialised into the
    HTML template.  The ``HtmlReporter`` converts it to a JSON dict and
    injects it into the ``__DASHBOARD_DATA_JSON__`` placeholder.
    """

    # --- Source information ---------------------------------------------------
    repo_path: str = ""
    branch: str = ""
    from_ref: str = ""
    to_ref: str = ""
    since_date: str = ""
    version: str = ""
    app_name: str = ""

    # --- Pipeline results -----------------------------------------------------
    total_changes: int = 0
    changes: tuple[ChangeEntry, ...] = ()
    pipeline_stats: tuple[PipelineStageStats, ...] = ()
    category_distribution: tuple[CategoryDistribution, ...] = ()

    # --- Highlights & breaking ------------------------------------------------
    highlights: tuple[ChangeEntry, ...] = ()
    breaking_changes: tuple[ChangeEntry, ...] = ()

    # --- Groups ---------------------------------------------------------------
    groups: tuple[ChangeGroupData, ...] = ()

    # --- Artifacts ------------------------------------------------------------
    artifacts: tuple[ArtifactPreview, ...] = ()

    # --- Metadata -------------------------------------------------------------
    generated_at: str = ""
    language: str = "en"
    audience: str = "changelog"
    output_format: str = "markdown"

    # --- Supported options (for wizard UI) ------------------------------------
    supported_audiences: tuple[str, ...] = (
        "technical",
        "user",
        "summary",
        "changelog",
        "customer",
        "executive",
        "narrative",
        "customer-narrative",
    )
    supported_formats: tuple[str, ...] = (
        "markdown",
        "plaintext",
        "json",
        "pdf",
        "docx",
    )

    # --- Source identity -------------------------------------------------------
    source_type: str = "local"  # "local", "github", "gitlab", "file", "multi"

    # --- Diagnostics (empty state) --------------------------------------------
    diagnostics: tuple[str, ...] = ()
    directory_exists: bool = True

    # --- Computed properties --------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return self.total_changes == 0 and len(self.changes) == 0

    @property
    def total_breaking(self) -> int:
        return len(self.breaking_changes)

    @property
    def total_highlights(self) -> int:
        return len(self.highlights)

    @property
    def categories_used(self) -> int:
        return len(self.category_distribution)

    @property
    def total_authors(self) -> int:
        authors: set[str] = set()
        for c in self.changes:
            authors.update(c.authors)
        return len(authors)

    @property
    def scopes_used(self) -> tuple[str, ...]:
        scopes: set[str] = set()
        for c in self.changes:
            if c.scope:
                scopes.add(c.scope)
        return tuple(sorted(scopes))
