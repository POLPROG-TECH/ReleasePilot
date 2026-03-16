# Narrative Output Mode


## Table of Contents

- [Two Narrative Audiences](#two-narrative-audiences)
  - [`narrative` — Fact-Based Narrative Summary](#narrative-fact-based-narrative-summary)
  - [`customer-narrative` — Client-Facing Narrative](#customer-narrative-client-facing-narrative)
- [How It Differs From Other Modes](#how-it-differs-from-other-modes)
- [Factual Grounding](#factual-grounding)
  - [What the system uses](#what-the-system-uses)
  - [What the system is allowed to infer](#what-the-system-is-allowed-to-infer)
  - [What the system is forbidden to invent](#what-the-system-is-forbidden-to-invent)
  - [Claim Validation](#claim-validation)
- [Architecture](#architecture)
  - [Pipeline stages](#pipeline-stages)
  - [Module structure](#module-structure)
  - [Inspecting the fact layer](#inspecting-the-fact-layer)
- [Examples](#examples)
  - [Narrative mode output](#narrative-mode-output)
- [Release Summary — v2.1.0](#release-summary-v210)
- [Overview](#overview)
- [⚠️ Important Changes](#important-changes)
  - [Customer narrative mode output](#customer-narrative-mode-output)
- [Product Update — v2.1.0](#product-update-v210)
- [What's Changed](#whats-changed)
- [⚠️ Important Changes](#important-changes)
- [Configuration](#configuration)
- [Supported Output Formats](#supported-output-formats)
- [Language Support](#language-support)

---
ReleasePilot can generate **continuous narrative prose** from your release changes, in addition to the standard bullet-based changelog formats.

This mode produces readable, paragraph-based text suitable for:
- Stakeholder communication
- Client-facing product updates
- Management briefs
- Customer newsletters

## Two Narrative Audiences

### `narrative` — Fact-Based Narrative Summary

Produces a full narrative covering all change categories. Suitable for internal stakeholders, team leads, and product managers who need a readable overview of everything that shipped.

```bash
releasepilot generate --audience narrative
releasepilot generate --audience narrative --format json
```

### `customer-narrative` — Client-Facing Narrative

Produces a polished, non-technical narrative that hides internal categories (refactoring, infrastructure, documentation) and focuses on user-visible changes. Suitable for customer emails, product update pages, and client communications.

```bash
releasepilot generate --audience customer-narrative
releasepilot generate --audience customer-narrative --app-name "MyProduct" --version 2.1.0
```

## How It Differs From Other Modes

| Mode | Format | Use Case |
|------|--------|----------|
| `changelog` | Bullet list | CHANGELOG.md, GitHub Releases |
| `technical` | Bullet list | Engineering teams |
| `summary` | Short bullet list | Quick scanning |
| `customer` | Bullet list | Customer-facing (bullets) |
| `executive` | Structured report | Management briefing |
| **`narrative`** | **Continuous prose** | **Stakeholder communication** |
| **`customer-narrative`** | **Continuous prose** | **Client-facing updates** |

The key difference: narrative modes produce **paragraphs of full sentences**, not bullet points. The output reads like a written summary, not a raw changelog.

## Factual Grounding

### What the system uses

The narrative is generated exclusively from:
- Commit messages and metadata
- PR titles and numbers (if available)
- Issue/ticket references (if available)
- Classification categories derived from the source data
- Quantitative counts (number of changes per category)

### What the system is allowed to infer

- Category grouping (e.g., "3 new features were added")
- Factual summarization (e.g., "This release includes 12 changes across 5 areas")
- Scope-based context (e.g., "in the authentication module")
- Breaking change notices when items are flagged as breaking

### What the system is forbidden to invent

- Business impact claims not supported by the data
- Marketing language (e.g., "revolutionary", "game-changer", "seamless")
- Speculative statements (e.g., "will transform", "expected to increase")
- User benefit claims not derivable from the change titles
- Performance numbers or metrics not present in the source
- Exaggerated language (e.g., "dramatically", "massive", "incredible")

### Claim Validation

The narrative pipeline includes a built-in validator that checks the generated text against:
1. **Forbidden language patterns** — marketing, speculative, and exaggerated terms
2. **Numeric claim verification** — numbers in the text must match the fact layer
3. **Category reference checking** — text must not reference categories absent from the data
4. **Fact count consistency** — total facts must match the sum of fact group counts

## Architecture

The narrative pipeline is **isolated from the standard release-notes pipeline** to prevent regressions.

```
Standard pipeline:   ReleaseNotes → MarkdownRenderer (bullets)
Executive pipeline:  ReleaseNotes → ExecutiveBrief → ExecutiveRenderer
Narrative pipeline:  ReleaseNotes → FactLayer → NarrativeBrief → NarrativeRenderer (prose)
                         ↑ shared boundary
```

### Pipeline stages

1. **Source collection** — same as standard pipeline (git log, structured JSON)
2. **Processing** — same classify → filter → deduplicate stages
3. **Audience transform** — applies category filtering appropriate for the mode
4. **Fact extraction** — converts ChangeItems into inspectable FactItems
5. **Narrative composition** — generates prose from the fact layer
6. **Validation** — checks the narrative against grounding rules
7. **Rendering** — outputs Markdown, plaintext, or JSON

### Module structure

The narrative pipeline follows the same architectural pattern as the executive
pipeline: audience logic in `audience/`, renderers in `rendering/`.

```
src/releasepilot/
├── audience/
│   ├── narrative.py          # Models, fact extraction, composition, validation
│   └── views.py              # Audience transforms (shared with all audiences)
└── rendering/
    ├── narrative_md.py       # Markdown prose renderer
    └── narrative_plain.py    # Plaintext prose renderer
```

### Inspecting the fact layer

The `NarrativeBrief` model exposes its underlying facts for auditability:

- `brief.fact_groups` — the grouped facts used to generate the narrative
- `brief.source_item_ids` — all ChangeItem IDs referenced
- `brief.total_facts` — total number of facts in the narrative

In JSON output, the full fact layer is included:

```bash
releasepilot generate --audience narrative --format json
```

```json
{
  "type": "narrative_brief",
  "mode": "narrative",
  "overview": "TestApp version 2.1.0 contains 10 changes spanning 5 areas...",
  "body_paragraphs": ["..."],
  "fact_groups": [
    {
      "theme": "New Features",
      "summary": "3 new features added",
      "facts": [
        {
          "text": "Add OAuth2 authentication: Full OAuth2 flow with PKCE",
          "category": "feature",
          "source_ids": ["item-1"],
          "is_highlight": false
        }
      ]
    }
  ],
  "total_facts": 10,
  "source_item_count": 10
}
```

## Examples

### Narrative mode output

```markdown
# MyApp

## Release Summary — v2.1.0

*June 15, 2025*
*Version 2.1.0*

---

## Overview

MyApp version 2.1.0 contains 10 changes spanning 5 areas. The changes
include 3 new features, 2 bug fixes, 1 security, 1 performance, and
3 improvements.

In the area of new features, 3 additions were made. Add OAuth2
authentication: Full OAuth2 flow with PKCE (in auth). Add dark mode
support (in ui). Implement search API (in api).

2 bug fixes were applied. Fix pagination off-by-one error (in api).
Fix session token refresh (in auth).

1 security-related change was made. Patch XSS vulnerability (in web).

1 performance optimization was implemented. Optimize dashboard
queries (in dashboard).

## ⚠️ Important Changes

This release includes 1 breaking change that may require attention.
Remove legacy API endpoints: The v1 endpoints have been removed.

---

*In total, version 2.1.0 comprises 10 changes across 5 areas.*

*This summary is based on 10 verified facts from 10 source changes.*
```

### Customer narrative mode output

```markdown
# MyApp

## Product Update — v2.1.0

*June 15, 2025*
*Version 2.1.0*

---

## What's Changed

MyApp version 2.1.0 includes 8 changes across 5 areas. This update
covers 3 new features, 2 bug fixes, 1 security, 1 performance, and
1 improvement.

This release introduces 3 new features. Add OAuth2 authentication:
Full OAuth2 flow with PKCE. Add dark mode support. Implement search API.

2 issues have been resolved in this update. Fix pagination off-by-one
error. Fix session token refresh.

1 security update has been applied. Patch XSS vulnerability.

## ⚠️ Important Changes

This release includes 1 breaking change that may require attention.
Remove legacy API endpoints: The v1 endpoints have been removed.

---

*Version 2.1.0 reflects 8 changes to the product.*

*This summary is based on 8 verified facts from 8 source changes.*
```

## Configuration

Set the narrative audience in `.releasepilot.json`:

```json
{
  "audience": "narrative",
  "app_name": "MyProduct",
  "version": "2.1.0"
}
```

Or use `customer-narrative`:

```json
{
  "audience": "customer-narrative",
  "app_name": "MyProduct"
}
```

## Supported Output Formats

| Format | Command |
|--------|---------|
| Markdown | `--format markdown` (default) |
| JSON (with fact layer) | `--format json` |
| Plaintext (preview) | `releasepilot preview --audience narrative` |

## Language Support

Narrative headings and labels are translated to all supported languages:

```bash
releasepilot generate --audience narrative --language de
releasepilot generate --audience customer-narrative --language fr
```
