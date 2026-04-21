"""Executive brief composer.

Transforms technical ReleaseNotes into a business-oriented ExecutiveBrief
suitable for management, leadership, board, and non-technical stakeholders.

Key transformations:
- Groups technical changes into business impact areas
- Rewrites titles in business-appropriate language
- Generates an executive summary from release metrics
- Extracts key achievements from highlights
- Identifies risks from breaking changes
- Produces actionable next-step recommendations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from releasepilot.domain.enums import ChangeCategory
from releasepilot.domain.models import ReleaseNotes, ReleaseRange

# ── Domain model ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ImpactArea:
    """A business-impact section in the executive brief."""

    title: str
    summary: str
    items: tuple[str, ...]


@dataclass(frozen=True)
class ExecutiveBrief:
    """Executive-oriented release summary.

    Designed for management, leadership, and board-level audiences.
    Every field contains business-language content, not raw technical data.
    """

    release_range: ReleaseRange
    executive_summary: str
    key_achievements: tuple[str, ...]
    impact_areas: tuple[ImpactArea, ...]
    risks: tuple[str, ...]
    next_steps: tuple[str, ...]
    metrics: dict[str, int] = field(default_factory=dict, hash=False)
    analysis_period: str = ""  # e.g. "last 30 days" or "since 2025-01-01"

    @property
    def report_title(self) -> str:
        rr = self.release_range
        if rr.version:
            return f"Release Brief - v{rr.version}"
        if rr.title:
            return f"Release Brief - {rr.title}"
        return "Release Brief"

    def localized_title(self, lang: str = "en") -> str:
        """Return report title with the 'Release Brief' part translated."""
        from releasepilot.i18n import get_label

        brief_label = get_label("release_brief", lang)
        rr = self.release_range
        if rr.version:
            return f"{brief_label} - v{rr.version}"
        if rr.title:
            return f"{brief_label} - {rr.title}"
        return brief_label

    @property
    def report_date(self) -> str:
        d = self.release_range.release_date or date.today()
        return d.strftime("%B %d, %Y")

    def localized_date(self, lang: str = "en") -> str:
        """Return report date formatted for the given language."""
        d = self.release_range.release_date or date.today()
        month_names: dict[str, tuple[str, ...]] = {
            "pl": (
                "",
                "stycznia",
                "lutego",
                "marca",
                "kwietnia",
                "maja",
                "czerwca",
                "lipca",
                "sierpnia",
                "września",
                "października",
                "listopada",
                "grudnia",
            ),
            "de": (
                "",
                "Januar",
                "Februar",
                "März",
                "April",
                "Mai",
                "Juni",
                "Juli",
                "August",
                "September",
                "Oktober",
                "November",
                "Dezember",
            ),
            "fr": (
                "",
                "janvier",
                "février",
                "mars",
                "avril",
                "mai",
                "juin",
                "juillet",
                "août",
                "septembre",
                "octobre",
                "novembre",
                "décembre",
            ),
            "es": (
                "",
                "enero",
                "febrero",
                "marzo",
                "abril",
                "mayo",
                "junio",
                "julio",
                "agosto",
                "septiembre",
                "octubre",
                "noviembre",
                "diciembre",
            ),
            "it": (
                "",
                "gennaio",
                "febbraio",
                "marzo",
                "aprile",
                "maggio",
                "giugno",
                "luglio",
                "agosto",
                "settembre",
                "ottobre",
                "novembre",
                "dicembre",
            ),
            "pt": (
                "",
                "janeiro",
                "fevereiro",
                "março",
                "abril",
                "maio",
                "junho",
                "julho",
                "agosto",
                "setembro",
                "outubro",
                "novembro",
                "dezembro",
            ),
            "nl": (
                "",
                "januari",
                "februari",
                "maart",
                "april",
                "mei",
                "juni",
                "juli",
                "augustus",
                "september",
                "oktober",
                "november",
                "december",
            ),
            "uk": (
                "",
                "січня",
                "лютого",
                "березня",
                "квітня",
                "травня",
                "червня",
                "липня",
                "серпня",
                "вересня",
                "жовтня",
                "листопада",
                "грудня",
            ),
            "cs": (
                "",
                "ledna",
                "února",
                "března",
                "dubna",
                "května",
                "června",
                "července",
                "srpna",
                "září",
                "října",
                "listopadu",
                "prosince",
            ),
        }
        months = month_names.get(lang)
        if months:
            return f"{d.day} {months[d.month]} {d.year}"
        return d.strftime("%B %d, %Y")


# ── Compose ──────────────────────────────────────────────────────────────────


def compose_executive_brief(
    notes: ReleaseNotes,
    *,
    analysis_period: str = "",
) -> ExecutiveBrief:
    """Transform ReleaseNotes into an ExecutiveBrief."""
    metrics = _collect_metrics(notes)
    summary = _generate_summary(notes, metrics)
    achievements = _extract_achievements(notes)
    impact_areas = _build_impact_areas(notes)
    risks = _extract_risks(notes)
    next_steps = _generate_next_steps(notes)

    return ExecutiveBrief(
        release_range=notes.release_range,
        executive_summary=summary,
        key_achievements=tuple(achievements),
        impact_areas=tuple(impact_areas),
        risks=tuple(risks),
        next_steps=tuple(next_steps),
        metrics=metrics,
        analysis_period=analysis_period,
    )


# ── Business theme mapping ───────────────────────────────────────────────────


_THEME_MAP: dict[ChangeCategory, tuple[str, str]] = {
    ChangeCategory.FEATURE: (
        "New Capabilities",
        "{n} new feature{s} {have} been delivered.",
    ),
    ChangeCategory.IMPROVEMENT: (
        "Product Improvements",
        "{n} enhancement{s} to existing features and workflows.",
    ),
    ChangeCategory.BUGFIX: (
        "Quality & Reliability",
        "{n} issue{s} resolved, improving overall stability.",
    ),
    ChangeCategory.PERFORMANCE: (
        "Performance & Efficiency",
        "{n} performance improvement{s} for faster, more efficient operations.",
    ),
    ChangeCategory.SECURITY: (
        "Security & Compliance",
        "{n} security enhancement{s} strengthening platform protection.",
    ),
    ChangeCategory.DEPRECATION: (
        "Planned Transitions",
        "{n} feature{s} scheduled for retirement in upcoming releases.",
    ),
    ChangeCategory.BREAKING: (
        "Important Changes",
        "{n} change{s} that may require action from dependent teams.",
    ),
}


def _theme_for(cat: ChangeCategory) -> tuple[str, str] | None:
    return _THEME_MAP.get(cat)


# ── Title transformation ────────────────────────────────────────────────────


_COMMIT_PREFIX_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|security|deprecate)"
    r"(\([\w./-]+\))?!?:\s*",
    re.IGNORECASE,
)


def _to_business_language(title: str) -> str:
    """Transform a technical title to business-appropriate language."""
    cleaned = _COMMIT_PREFIX_RE.sub("", title)
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    cleaned = cleaned.rstrip(".")
    return cleaned or title


# ── Metrics ──────────────────────────────────────────────────────────────────


def _collect_metrics(notes: ReleaseNotes) -> dict[str, int]:
    counts: dict[str, int] = {"total_changes": notes.total_changes}
    category_key_map = {
        ChangeCategory.FEATURE: "features",
        ChangeCategory.IMPROVEMENT: "improvements",
        ChangeCategory.BUGFIX: "bugfixes",
        ChangeCategory.PERFORMANCE: "performance",
        ChangeCategory.SECURITY: "security",
        ChangeCategory.DEPRECATION: "deprecations",
        ChangeCategory.BREAKING: "breaking",
    }
    for group in notes.groups:
        key = category_key_map.get(group.category)
        if key:
            counts[key] = len(group.items)
    counts["breaking"] = len(notes.breaking_changes)
    counts["highlights"] = len(notes.highlights)
    return counts


# ── Summary generation ───────────────────────────────────────────────────────


def _plural(n: int, singular: str, plural_form: str | None = None) -> str:
    return singular if n == 1 else (plural_form or singular + "s")


def _generate_summary(notes: ReleaseNotes, metrics: dict[str, int]) -> str:
    """Generate a 3-5 sentence executive summary emphasising outcomes."""
    parts: list[str] = []

    features = metrics.get("features", 0)
    bugfixes = metrics.get("bugfixes", 0)
    improvements = metrics.get("improvements", 0)
    security = metrics.get("security", 0)
    performance = metrics.get("performance", 0)

    # Main delivery sentence
    delivery_parts: list[str] = []
    if features:
        delivery_parts.append(f"{features} new {_plural(features, 'capability', 'capabilities')}")
    if bugfixes:
        delivery_parts.append(f"{bugfixes} quality {_plural(bugfixes, 'improvement')}")
    if improvements:
        delivery_parts.append(f"{improvements} product {_plural(improvements, 'enhancement')}")
    if performance:
        delivery_parts.append(f"{performance} performance {_plural(performance, 'optimization')}")

    if delivery_parts:
        joined = _join_natural(delivery_parts)
        parts.append(f"This release delivers {joined}.")
    else:
        parts.append(
            f"This release includes {metrics['total_changes']} "
            f"{_plural(metrics['total_changes'], 'change')}."
        )

    # Business-value sentence
    if features and bugfixes:
        parts.append(
            "The combined improvements strengthen both product capabilities "
            "and platform reliability, reducing operational risk while "
            "expanding the feature set."
        )
    elif features:
        parts.append(
            "These additions expand the platform's capabilities and "
            "open new workflows for end users."
        )
    elif bugfixes:
        parts.append(
            "These improvements increase overall stability and reduce "
            "the likelihood of user-facing issues."
        )

    # Security note
    if security:
        parts.append(
            f"The release also includes {security} security "
            f"{_plural(security, 'enhancement')} strengthening "
            f"platform protection and compliance posture."
        )

    # Breaking changes warning
    breaking = metrics.get("breaking", 0)
    if breaking:
        parts.append(
            f"Note: {breaking} {_plural(breaking, 'change')} may require "
            f"attention from affected teams before or after deployment."
        )

    return " ".join(parts)


def _join_natural(items: list[str]) -> str:
    """Join items with commas and 'and': 'a, b, and c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


# ── Achievements ─────────────────────────────────────────────────────────────


def _extract_achievements(notes: ReleaseNotes) -> list[str]:
    """Extract top achievements from highlights, rewritten for executives."""
    achievements: list[str] = []
    max_achievements = 7

    for item in notes.highlights[:max_achievements]:
        title = _to_business_language(item.title)
        if item.description:
            short_desc = item.description.split(".")[0].strip()
            if short_desc and len(short_desc) < 120:
                achievements.append(f"{title} - {short_desc}")
                continue
        achievements.append(title)

    # If fewer than 3 achievements from highlights, pull top features
    if len(achievements) < 3:
        for group in notes.groups:
            if group.category == ChangeCategory.FEATURE:
                for item in group.items:
                    title = _to_business_language(item.title)
                    if title not in achievements:
                        achievements.append(title)
                    if len(achievements) >= 5:
                        break
            if len(achievements) >= 5:
                break

    return achievements[:max_achievements]


# ── Impact areas ─────────────────────────────────────────────────────────────


def _build_impact_areas(notes: ReleaseNotes) -> list[ImpactArea]:
    """Build business-oriented impact areas from change groups."""
    areas: list[ImpactArea] = []

    for group in notes.groups:
        theme = _theme_for(group.category)
        if not theme:
            continue

        theme_title, summary_template = theme
        n = len(group.items)
        s = "" if n == 1 else "s"
        have = "has" if n == 1 else "have"
        summary = summary_template.format(n=n, s=s, have=have)

        items = tuple(_to_business_language(item.title) for item in group.items)

        areas.append(ImpactArea(title=theme_title, summary=summary, items=items))

    return areas


# ── Risks ────────────────────────────────────────────────────────────────────


def _extract_risks(notes: ReleaseNotes) -> list[str]:
    """Extract risk items from breaking changes and deprecations."""
    risks: list[str] = []

    for item in notes.breaking_changes:
        title = _to_business_language(item.title)
        if item.description:
            short_desc = item.description.split(".")[0].strip()
            if short_desc and len(short_desc) < 150:
                risks.append(f"{title} - {short_desc}")
                continue
        risks.append(title)

    for group in notes.groups:
        if group.category == ChangeCategory.DEPRECATION:
            for item in group.items:
                risks.append(f"Planned deprecation: {_to_business_language(item.title)}")

    return risks


# ── Next steps ───────────────────────────────────────────────────────────────


def _generate_next_steps(notes: ReleaseNotes) -> list[str]:
    """Generate actionable next-step recommendations."""
    steps: list[str] = []

    if notes.breaking_changes:
        steps.append("Review and communicate breaking changes to affected teams")

    has_cat = {g.category for g in notes.groups}

    if ChangeCategory.SECURITY in has_cat:
        steps.append("Verify security improvements are active in production")

    if ChangeCategory.PERFORMANCE in has_cat:
        steps.append("Validate performance improvements against baseline benchmarks")

    if ChangeCategory.DEPRECATION in has_cat:
        steps.append("Plan migration timeline for deprecated features")

    steps.append("Monitor application health metrics after deployment")
    steps.append("Update stakeholder communications and release documentation")

    return steps
