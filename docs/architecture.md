# Architecture Guide


## Table of Contents

- [Overview](#overview)
- [Package Structure](#package-structure)
- [Domain Model](#domain-model)
  - [ChangeItem](#changeitem)
  - [ReleaseRange](#releaserange)
  - [ChangeGroup](#changegroup)
  - [ReleaseNotes](#releasenotes)
- [Extension Points](#extension-points)
  - [Adding a new source provider](#adding-a-new-source-provider)
  - [Adding a new output format](#adding-a-new-output-format)
  - [Adding a new audience view](#adding-a-new-audience-view)
- [Design Decisions](#design-decisions)
  - [Frozen dataclasses](#frozen-dataclasses)
  - [Explicit sort keys](#explicit-sort-keys)
  - [Conservative deduplication](#conservative-deduplication)
  - [Protocol-based extension](#protocol-based-extension)
- [Narrative Pipeline](#narrative-pipeline)
  - [Architecture](#architecture)
  - [Pipeline stages](#pipeline-stages)
  - [Why this placement](#why-this-placement)

---
## Overview

ReleasePilot uses a **pipeline architecture** where data flows through clearly separated stages, each with a single responsibility. Three independent output pipelines branch from a shared `ReleaseNotes` boundary to serve different audiences.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CLI / Config                                                           │
│  ┌──────────┐  ┌────────────┐  ┌─────────────────────────────────────┐  │
│  │ Commands │──│ Settings   │──│ Pipeline Orchestrator               │  │
│  └──────────┘  └────────────┘  └──────────────┬──────────────────────┘  │
└───────────────────────────────────────────────┼──────────────────────────┘
                                                │
┌───────────────────────────────────────────────┼──────────────────────────┐
│  Source Collection                            ▼                          │
│  ┌──────────────────┐   ┌──────────────────────────┐                    │
│  │ Git log / tags   │   │ Structured JSON files     │                   │
│  └────────┬─────────┘   └────────────┬─────────────┘                    │
│           └──────────┬───────────────┘                                  │
│                      ▼                                                  │
│            list[ChangeItem]                                             │
└──────────────────────┬──────────────────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────────────────┐
│  Processing          ▼                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ Classifier   │─▷│ Filter       │─▷│ Deduplicator │─▷│ Grouper    │  │
│  │ (categorize) │  │ (noise/cats) │  │ (exact/near) │  │ (aggregate)│  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────┬──────┘  │
└──────────────────────────────────────────────────────────────┼──────────┘
                                                               │
┌──────────────────────────────────────────────────────────────┼──────────┐
│  Audience + Composition                                      ▼          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                       ReleaseNotes                               │   │
│  │  (groups, highlights, breaking changes, metadata, stats)         │   │
│  └─────────┬─────────────────────┬─────────────────────┬───────────┘   │
│            │                     │                     │               │
│   ┌────────▼────────┐  ┌────────▼─────────┐  ┌────────▼──────────┐   │
│   │ Audience Views  │  │ Executive Brief  │  │ Narrative Brief   │   │
│   │ (views.py)      │  │ (executive.py)   │  │ (narrative.py)    │   │
│   │ filter + polish │  │ compose business │  │ extract facts     │   │
│   │                 │  │ summary          │  │ compose prose     │   │
│   │                 │  │                  │  │ validate claims   │   │
│   └────────┬────────┘  └────────┬─────────┘  └────────┬──────────┘   │
└────────────┼─────────────────────┼─────────────────────┼──────────────┘
             │                     │                     │
┌────────────┼─────────────────────┼─────────────────────┼──────────────┐
│  Rendering ▼                     ▼                     ▼              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │ Standard         │  │ Executive        │  │ Narrative        │    │
│  │ ─────────────    │  │ ─────────────    │  │ ─────────────    │    │
│  │ • Markdown       │  │ • Markdown       │  │ • Markdown       │    │
│  │ • Plaintext      │  │ • PDF            │  │ • Plaintext      │    │
│  │ • JSON           │  │ • DOCX           │  │ • JSON           │    │
│  │ • PDF / DOCX     │  │ • JSON           │  │                  │    │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘    │
└───────────────────────────────────────────────────────────────────────┘
```

**Key architectural property:** The three output pipelines (Standard, Executive, Narrative) are fully independent after the `ReleaseNotes` boundary. Changes to one pipeline cannot regress another.

This design was chosen as the best balance between:

- **Extensibility** — New stages can be inserted at any point without modifying existing ones
- **Correctness** — Each stage is a pure function (input → output) except Source Collection, making them deterministic and easy to test
- **Output quality** — Dedicated filtering, dedup, and audience stages ensure polished results
- **Maintainability** — Each module has exactly one responsibility
- **Deterministic behavior** — Explicit sort keys at every boundary guarantee stable output
- **Future integration** — Protocol-based extension points support new sources, formats, and audience views

## Package Structure

```
src/releasepilot/
├── __init__.py         # Package root, version
├── cli/
│   ├── app.py          # Click CLI commands and option handling
│   └── guide.py        # Interactive guided workflow
├── config/
│   └── settings.py     # Frozen dataclass settings, filter/render config
├── domain/
│   ├── enums.py        # ChangeCategory, Audience, OutputFormat, Importance
│   └── models.py       # ChangeItem, ReleaseRange, ChangeGroup, ReleaseNotes
├── pipeline/
│   └── orchestrator.py # Wires all stages together
├── sources/
│   ├── protocol.py     # SourceCollector protocol
│   ├── git.py          # Git log source collector
│   └── structured.py   # JSON file source collector
├── processing/
│   ├── classifier.py   # Conventional Commits + keyword classification
│   ├── filter.py       # Noise pattern + category + importance filtering
│   ├── dedup.py        # Exact, PR-based, and near-duplicate removal
│   └── grouper.py      # Category grouping + highlight/breaking extraction
├── audience/
│   ├── views.py        # Audience-specific transformations (filter + polish)
│   ├── executive.py    # ExecutiveBrief model + composition logic
│   └── narrative.py    # NarrativeBrief model + fact extraction + composition + validation
├── rendering/
│   ├── protocol.py     # Renderer protocol
│   ├── markdown.py     # Standard Markdown renderer (bullet lists)
│   ├── plaintext.py    # Terminal plaintext renderer
│   ├── json_renderer.py # Structured JSON renderer
│   ├── pdf.py          # PDF renderer
│   ├── docx_renderer.py # DOCX renderer
│   ├── executive_md.py # Executive Markdown renderer
│   ├── executive_pdf.py # Executive PDF renderer
│   ├── executive_docx.py # Executive DOCX renderer
│   ├── narrative_md.py # Narrative Markdown renderer (prose)
│   └── narrative_plain.py # Narrative plaintext renderer
└── i18n/
    └── labels.py       # Translated UI labels (10 languages)
```

The directory layout mirrors the architecture diagram above:

- **audience/** contains composition logic — transforming `ReleaseNotes` into audience-specific models (`ExecutiveBrief`, `NarrativeBrief`) or filtered views
- **rendering/** contains all output formatting — converting composed models into Markdown, PDF, DOCX, JSON, or plaintext

## Domain Model

The domain model is the contract between pipeline stages:

### ChangeItem

The central domain object. Every source collector produces `ChangeItem` instances, and every downstream stage consumes them.

Key fields: `id`, `title`, `description`, `category`, `scope`, `importance`, `is_breaking`, `source`, `authors`, `timestamp`

### ReleaseRange

Defines the scope of changes: `from_ref`, `to_ref`, `version`, `title`, `release_date`

### ChangeGroup

A collection of `ChangeItem` instances under one `ChangeCategory`, with deterministic sort order.

### ReleaseNotes

The final composed output: groups, highlights, breaking changes, metadata. This is what renderers consume.

## Extension Points

### Adding a new source provider

1. Create a new module in `sources/`
2. Implement the `SourceCollector` protocol:
   ```python
   class GitHubSourceCollector:
       def collect(self, release_range: ReleaseRange) -> list[ChangeItem]:
           ...
   ```
3. Wire it into `pipeline/orchestrator.py`

### Adding a new output format

1. Create a new module in `rendering/`
2. Implement the `Renderer` protocol:
   ```python
   class HtmlRenderer:
       def render(self, notes: ReleaseNotes, config: RenderConfig) -> str:
           ...
   ```
3. Add the format to `OutputFormat` enum and the renderer map in the orchestrator

### Adding a new audience view

1. Add a transform function to `audience/views.py`
2. Register it in the `apply_audience` function's dispatch map

## Design Decisions

### Frozen dataclasses

All domain models are frozen (`frozen=True`) for:
- Immutability guarantees through the pipeline
- Safe use as dict keys / set members
- Clear data flow (no mutation surprises)

### Explicit sort keys

Every model that participates in ordering has an explicit `sort_key` property. This ensures deterministic output regardless of source collection order.

### Conservative deduplication

Near-duplicate detection requires ≥3 meaningful tokens and ≥80% overlap. This avoids false positives while catching genuinely duplicate entries.

### Protocol-based extension

Source collectors and renderers use Python `Protocol` (structural subtyping) rather than ABC inheritance. This keeps the coupling loose and avoids import-time dependencies on abstract base classes.

## Narrative Pipeline

The narrative pipeline (`audience/narrative.py` + `rendering/narrative_*.py`) produces **continuous prose** instead of bullet lists. It follows the same structural pattern as the executive pipeline.

### Architecture

| Layer | Executive | Narrative |
|-------|-----------|-----------|
| **Composition** | `audience/executive.py` | `audience/narrative.py` |
| **Model** | `ExecutiveBrief` | `NarrativeBrief` |
| **Renderers** | `rendering/executive_*.py` | `rendering/narrative_*.py` |
| **Intermediate layer** | — | `FactItem` / `FactGroup` (inspectable) |
| **Validation** | — | Claim validation against fact layer |

### Pipeline stages

1. **Fact extraction** — converts `ChangeItem` instances into inspectable `FactItem` / `FactGroup` models
2. **Narrative composition** — generates prose paragraphs from the fact layer (deterministic, no LLM)
3. **Claim validation** — checks generated text for forbidden language, numeric inconsistencies, and phantom categories
4. **Rendering** — formats the `NarrativeBrief` as Markdown, plaintext, or JSON

### Why this placement

The narrative composition logic lives in `audience/` (not in a separate top-level module) because it follows the same pattern as the executive pipeline: it transforms `ReleaseNotes` into an audience-specific model. The renderers live in `rendering/` because they are output formatters. This keeps the architecture layered and consistent — composition in one place, formatting in another.

See [docs/narrative-mode.md](narrative-mode.md) for usage documentation, grounding rules, and output examples.
