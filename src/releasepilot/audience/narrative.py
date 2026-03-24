"""Fact-grounded narrative pipeline for ReleasePilot.

Transforms ``ReleaseNotes`` into a ``NarrativeBrief`` — a continuous prose
summary of release changes suitable for stakeholder communication,
client-facing updates, and management briefs.

This module mirrors the executive pipeline (``audience/executive.py``)
in structure: composition logic and domain models live here; renderers
live in ``rendering/narrative_md.py`` and ``rendering/narrative_plain.py``.

Architecture
============
::

    Standard pipeline:  ReleaseNotes → MarkdownRenderer (bullets)
    Executive pipeline: ReleaseNotes → ExecutiveBrief  → ExecutiveRenderer
    Narrative pipeline: ReleaseNotes → NarrativeBrief  → NarrativeRenderer (prose)
                            ↑ shared boundary

Truthfulness guarantee
======================
Every sentence is derived from an inspectable fact layer, not from
unconstrained text generation.  The ``validate_narrative`` function
can verify that no unsupported claims have been introduced.

Stages
======
1. **Fact extraction** — ``ChangeItem`` → ``FactItem`` / ``FactGroup``
2. **Narrative composition** — ``FactGroup`` list → ``NarrativeBrief``
3. **Claim validation** — checks the brief against grounding rules

Implementation is split across focused sub-modules:

- ``narrative_models`` — domain dataclasses
- ``narrative_facts`` — fact extraction
- ``narrative_compose`` — prose generation
- ``narrative_validate`` — claim validation

This file re-exports the full public API for backwards compatibility.
"""

from releasepilot.audience.narrative_compose import (  # noqa: F401
    compose_narrative,
)
from releasepilot.audience.narrative_facts import (  # noqa: F401
    collect_all_source_ids,
    extract_fact_groups,
    extract_facts,
)
from releasepilot.audience.narrative_models import (  # noqa: F401
    FactGroup,
    FactItem,
    NarrativeBrief,
    ValidationIssue,
)
from releasepilot.audience.narrative_validate import (  # noqa: F401
    validate_narrative,
)

__all__ = [
    "FactGroup",
    "FactItem",
    "NarrativeBrief",
    "ValidationIssue",
    "collect_all_source_ids",
    "compose_narrative",
    "extract_fact_groups",
    "extract_facts",
    "validate_narrative",
]
