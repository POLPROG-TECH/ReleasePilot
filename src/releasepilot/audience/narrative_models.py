"""Domain models for the narrative pipeline.

Defines the core dataclasses used across the narrative subsystem:
``FactItem``, ``FactGroup``, ``NarrativeBrief``, and ``ValidationIssue``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import ReleaseRange

# ════════════════════════════════════════════════════════════════════════════
# Fact models
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FactItem:
    """A single verified fact extracted from source change data.

    Every fact is traceable: ``source_ids`` links back to the original
    ChangeItem identifiers so the narrative can be audited.
    """

    text: str
    category: ChangeCategory
    source_ids: tuple[str, ...] = ()
    scope: str = ""
    is_breaking: bool = False
    is_highlight: bool = False


@dataclass(frozen=True)
class FactGroup:
    """A thematic group of related facts.

    Groups are used to structure the narrative into coherent paragraphs.
    Each group has a human-readable theme label and a summary sentence.
    """

    theme: str
    summary: str
    facts: tuple[FactItem, ...]
    category: ChangeCategory = ChangeCategory.OTHER

    @property
    def count(self) -> int:
        return len(self.facts)


# ════════════════════════════════════════════════════════════════════════════
# Brief model
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class NarrativeBrief:
    """A fact-grounded narrative summary of a release.

    This is the central output model of the narrative pipeline.
    Every field is derived from verified facts, not from free-form generation.
    """

    release_range: ReleaseRange
    overview: str
    body_paragraphs: tuple[str, ...] = ()
    breaking_notice: str = ""
    closing: str = ""
    fact_groups: tuple[FactGroup, ...] = ()
    total_facts: int = 0
    source_item_ids: frozenset[str] = field(default_factory=frozenset)
    mode: str = "narrative"

    @property
    def report_title(self) -> str:
        rr = self.release_range
        label = "Product Update" if self.mode == "customer-narrative" else "Release Summary"
        if rr.version:
            return f"{label} - v{rr.version}"
        if rr.title:
            return f"{label} - {rr.title}"
        return label

    def localized_title(self, lang: str = "en") -> str:
        """Return report title with the label portion translated."""
        from releasepilot.i18n import get_label

        if self.mode == "customer-narrative":
            label = get_label("customer_narrative_title", lang)
        else:
            label = get_label("narrative_title", lang)
        rr = self.release_range
        if rr.version:
            return f"{label} - v{rr.version}"
        if rr.title:
            return f"{label} - {rr.title}"
        return label

    @property
    def report_date(self) -> str:
        d = self.release_range.release_date or date.today()
        return d.strftime("%B %d, %Y")

    @property
    def full_text(self) -> str:
        """The complete narrative as a single string (for validation)."""
        parts = [self.overview]
        parts.extend(self.body_paragraphs)
        if self.breaking_notice:
            parts.append(self.breaking_notice)
        if self.closing:
            parts.append(self.closing)
        return "\n\n".join(parts)


# ════════════════════════════════════════════════════════════════════════════
# Validation model
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding."""

    severity: str  # "error" or "warning"
    rule: str  # machine-readable rule name
    message: str  # human-readable description
