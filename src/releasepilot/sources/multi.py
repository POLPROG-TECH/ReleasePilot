"""Multi-repository source collector.

Aggregates commits from multiple ``SourceCollector`` instances into a single
combined list. Each item retains provenance via ``metadata["app_label"]`` so
renderers can group output by repository.

The release range / scope is shared - all repositories use the same range
definition, comparison window, and scope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from releasepilot.domain.models import ChangeItem, ReleaseRange

logger = logging.getLogger("releasepilot.multi_collector")


@dataclass(frozen=True)
class RepoCollectionResult:
    """Result of collecting from a single repository within a multi-repo run."""

    app_label: str
    items: tuple[ChangeItem, ...]
    error: str = ""
    success: bool = True


class MultiRepoCollectionError(Exception):
    """Raised when ALL repositories fail to collect."""


class MultiRepoCollector:
    """Collects and aggregates commits from multiple SourceCollector instances.

    Each sub-collector is tagged with an ``app_label`` that is injected into
    every ChangeItem's metadata for provenance tracking.

    Usage::

        multi = MultiRepoCollector()
        multi.add("Frontend", frontend_collector)
        multi.add("Backend", backend_collector)
        items = multi.collect(release_range)
    """

    def __init__(self) -> None:
        self._collectors: list[tuple[str, object]] = []

    def add(self, app_label: str, collector: object) -> None:
        """Register a source collector with its application label.

        The collector must implement the ``SourceCollector`` protocol
        (i.e. have a ``collect(release_range)`` method).
        """
        self._collectors.append((app_label, collector))

    @property
    def count(self) -> int:
        """Number of registered collectors."""
        return len(self._collectors)

    def collect(self, release_range: ReleaseRange) -> list[ChangeItem]:
        """Collect commits from all registered sources using a shared range.

        Each item gets ``metadata["app_label"]`` set to the source's label.
        Items are sorted by timestamp (newest first) then by app_label for
        deterministic ordering.

        If some repos fail, their errors are logged but collection continues.
        Raises ``MultiRepoCollectionError`` only if ALL repos fail.
        """
        all_items: list[ChangeItem] = []
        results: list[RepoCollectionResult] = []
        success_count = 0

        for app_label, collector in self._collectors:
            try:
                logger.info("Collecting from '%s'…", app_label)
                items = collector.collect(release_range)  # type: ignore[union-attr]

                # Inject app_label into each item's metadata
                labelled: list[ChangeItem] = []
                for item in items:
                    meta = dict(item.metadata)
                    meta["app_label"] = app_label
                    labelled.append(
                        ChangeItem(
                            id=item.id,
                            title=item.title,
                            description=item.description,
                            category=item.category,
                            scope=item.scope,
                            importance=item.importance,
                            is_breaking=item.is_breaking,
                            source=item.source,
                            authors=item.authors,
                            timestamp=item.timestamp,
                            raw_message=item.raw_message,
                            metadata=meta,
                        )
                    )

                all_items.extend(labelled)
                results.append(
                    RepoCollectionResult(
                        app_label=app_label,
                        items=tuple(labelled),
                        success=True,
                    )
                )
                success_count += 1
                logger.info("Collected %d commits from '%s'", len(labelled), app_label)

            except Exception as exc:
                logger.error("Failed to collect from '%s': %s", app_label, exc)
                results.append(
                    RepoCollectionResult(
                        app_label=app_label,
                        items=(),
                        error=str(exc),
                        success=False,
                    )
                )

        if success_count == 0 and self._collectors:
            errors = "; ".join(f"{r.app_label}: {r.error}" for r in results if not r.success)
            raise MultiRepoCollectionError(
                f"All {len(self._collectors)} repositories failed to collect. Errors: {errors}"
            )

        # Sort by timestamp (newest first), then by app_label for stability
        all_items.sort(
            key=lambda item: (
                -(item.timestamp.timestamp() if item.timestamp else 0),
                item.metadata.get("app_label", ""),
                item.title.lower(),
            )
        )

        logger.info(
            "Multi-repo collection complete: %d items from %d/%d sources",
            len(all_items),
            success_count,
            len(self._collectors),
        )

        return all_items

    def collect_with_results(
        self, release_range: ReleaseRange
    ) -> tuple[list[ChangeItem], list[RepoCollectionResult]]:
        """Like collect() but also returns per-repo results for diagnostics."""
        all_items: list[ChangeItem] = []
        results: list[RepoCollectionResult] = []

        for app_label, collector in self._collectors:
            try:
                items = collector.collect(release_range)  # type: ignore[union-attr]
                labelled = []
                for item in items:
                    meta = dict(item.metadata)
                    meta["app_label"] = app_label
                    labelled.append(
                        ChangeItem(
                            id=item.id,
                            title=item.title,
                            description=item.description,
                            category=item.category,
                            scope=item.scope,
                            importance=item.importance,
                            is_breaking=item.is_breaking,
                            source=item.source,
                            authors=item.authors,
                            timestamp=item.timestamp,
                            raw_message=item.raw_message,
                            metadata=meta,
                        )
                    )
                all_items.extend(labelled)
                results.append(
                    RepoCollectionResult(
                        app_label=app_label,
                        items=tuple(labelled),
                        success=True,
                    )
                )
            except Exception as exc:
                results.append(
                    RepoCollectionResult(
                        app_label=app_label,
                        items=(),
                        error=str(exc),
                        success=False,
                    )
                )

        all_items.sort(
            key=lambda item: (
                -(item.timestamp.timestamp() if item.timestamp else 0),
                item.metadata.get("app_label", ""),
                item.title.lower(),
            )
        )

        return all_items, results
