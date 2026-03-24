"""Dashboard use-case — builds DashboardData from the pipeline orchestrator."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

from releasepilot.config.settings import Settings
from releasepilot.dashboard.schema import (
    ArtifactPreview,
    CategoryDistribution,
    ChangeEntry,
    ChangeGroupData,
    DashboardData,
    PipelineStageStats,
)
from releasepilot.domain.enums import Audience, ChangeCategory, OutputFormat
from releasepilot.domain.models import ChangeItem, ReleaseNotes
from releasepilot.pipeline.orchestrator import (
    PipelineError,
    PipelineStats,
    build_release_range,
    collect,
    compose,
    process_with_stats,
    render,
)


class DashboardUseCase:
    """Orchestrate the full pipeline and return a :class:`DashboardData`."""

    def execute(self, settings: Settings) -> DashboardData:
        """Run the pipeline and build a complete dashboard payload."""
        try:
            release_range = build_release_range(settings)
            raw_items = collect(settings, release_range)
            processed, stats = process_with_stats(settings, raw_items)
            notes = compose(settings, processed, release_range, stats)

            entries = tuple(_to_entry(item) for item in processed)
            groups = _build_groups(notes)
            distribution = _build_distribution(stats)
            pipeline_stats = _build_pipeline_stats(stats)
            highlights = tuple(e for e in entries if e.importance == "high")
            breaking = tuple(e for e in entries if e.breaking)
            artifacts = _build_artifacts(settings, notes)

            return DashboardData(
                repo_path=settings.repo_path,
                branch=settings.branch,
                from_ref=settings.from_ref,
                to_ref=settings.to_ref,
                since_date=settings.since_date,
                version=settings.version,
                app_name=settings.app_name,
                total_changes=stats.final,
                changes=entries,
                pipeline_stats=pipeline_stats,
                category_distribution=distribution,
                highlights=highlights,
                breaking_changes=breaking,
                groups=groups,
                artifacts=artifacts,
                generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
                language=settings.language,
                audience=settings.audience.value,
                output_format=settings.output_format.value,
                directory_exists=Path(settings.repo_path).is_dir(),
            )
        except PipelineError as exc:
            return DashboardData(
                repo_path=settings.repo_path,
                since_date=settings.since_date,
                diagnostics=(str(exc),),
                directory_exists=Path(settings.repo_path).is_dir(),
                generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        except Exception as exc:  # noqa: BLE001
            return DashboardData(
                repo_path=settings.repo_path,
                diagnostics=(f"Unexpected error: {exc}",),
                generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_entry(item: ChangeItem) -> ChangeEntry:
    """Convert a domain ``ChangeItem`` into a dashboard ``ChangeEntry``."""
    return ChangeEntry(
        hash=item.source.short_hash,
        title=item.title,
        category=item.category.value,
        category_emoji=item.category.display_label.split(" ")[0],
        scope=item.scope,
        authors=item.authors,
        date=item.timestamp.strftime("%Y-%m-%d") if item.timestamp else "",
        importance=item.importance.value,
        breaking=item.is_breaking,
        pr_number=item.source.pr_number,
        source="structured" if not item.source.commit_hash else "git",
    )


def _build_groups(notes: ReleaseNotes) -> tuple[ChangeGroupData, ...]:
    """Map ``ReleaseNotes.groups`` into dashboard-friendly group data."""
    return tuple(
        ChangeGroupData(
            category=group.category.value,
            emoji=group.category.display_label.split(" ")[0],
            count=len(group.items),
            items=tuple(_to_entry(item) for item in group.items),
        )
        for group in notes.groups
    )


def _build_distribution(stats: PipelineStats) -> tuple[CategoryDistribution, ...]:
    """Derive a per-category distribution from ``PipelineStats``."""
    total = stats.final
    distribution: list[CategoryDistribution] = []
    for cat in ChangeCategory:
        count = stats.category_counts.get(cat.value, 0)
        if count > 0:
            distribution.append(
                CategoryDistribution(
                    category=cat.value,
                    emoji=cat.display_label.split(" ")[0],
                    count=count,
                    percentage=round(count / total * 100, 1) if total else 0,
                )
            )
    return tuple(distribution)


def _build_pipeline_stats(stats: PipelineStats) -> tuple[PipelineStageStats, ...]:
    """Build the four canonical pipeline stage stats."""
    return (
        PipelineStageStats("collected", stats.raw, stats.raw),
        PipelineStageStats("classified", stats.raw, stats.raw),
        PipelineStageStats("filtered", stats.raw, stats.after_filter),
        PipelineStageStats("deduplicated", stats.after_filter, stats.after_dedup),
    )


def _build_artifacts(
    settings: Settings,
    notes: ReleaseNotes,
) -> tuple[ArtifactPreview, ...]:
    """Render artifacts for ALL audience × text-format combinations.

    Binary formats (PDF, DOCX) are skipped since they cannot be previewed
    inline in the HTML dashboard.  Each combination that renders successfully
    is included; failures are silently skipped.
    """
    previews: list[ArtifactPreview] = []
    text_formats = (OutputFormat.MARKDOWN, OutputFormat.PLAINTEXT, OutputFormat.JSON)

    for audience in Audience:
        for fmt in text_formats:
            try:
                variant = dataclasses.replace(
                    settings,
                    audience=audience,
                    output_format=fmt,
                )
                content = render(variant, notes)
                previews.append(
                    ArtifactPreview(
                        audience=audience.value,
                        format=fmt.value,
                        content=content,
                        size_bytes=len(content.encode()),
                    )
                )
            except Exception:  # noqa: BLE001
                pass

    return tuple(previews)
