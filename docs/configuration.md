# Configuration Reference


## Table of Contents

- [Configuration Sources](#configuration-sources)
- [Config File](#config-file)
  - [Search Order](#search-order)
  - [Supported Fields](#supported-fields)
  - [pyproject.toml Integration](#pyprojecttoml-integration)
  - [Override Behavior](#override-behavior)
  - [Validation](#validation)
- [CLI Options](#cli-options)
  - [Global Options](#global-options)
  - [Output Options (generate / export)](#output-options-generate-export)
- [Optional Dependencies](#optional-dependencies)
- [Structured Input Format](#structured-input-format)
  - [Field Reference](#field-reference)
  - [Categories](#categories)
- [Noise Filtering](#noise-filtering)
- [Conventional Commits](#conventional-commits)
- [Date-Range Mode](#date-range-mode)
  - [Branch Validation](#branch-validation)
  - [Requested vs Effective Range](#requested-vs-effective-range)
- [Guided Workflow](#guided-workflow)
  - [Remote URL support](#remote-url-support)
  - [Smart defaults](#smart-defaults)
  - [Progress feedback](#progress-feedback)
  - [Interactive navigation](#interactive-navigation)
  - [Input validation](#input-validation)
- [Dry-Run Mode](#dry-run-mode)
- [Pre-flight Validation](#pre-flight-validation)
- [Empty Release Detection](#empty-release-detection)
- [Executive Audience Mode](#executive-audience-mode)
  - [What it does](#what-it-does)
  - [Document structure](#document-structure)
  - [Usage examples](#usage-examples)
  - [Guided workflow](#guided-workflow)
  - [Audience comparison](#audience-comparison)
  - [Date-range history bounds](#date-range-history-bounds)
- [Title Composition](#title-composition)
  - [Document Title Hierarchy](#document-title-hierarchy)
- [Translation](#translation)
  - [Supported languages](#supported-languages)
  - [What is translated](#what-is-translated)
  - [Architecture](#architecture)
  - [Adding a new language](#adding-a-new-language)
- [Multi-Repository Generation](#multi-repository-generation)
  - [Usage](#usage)
  - [Behavior](#behavior)
- [Pipeline Transparency](#pipeline-transparency)
  - [Pipeline Stages](#pipeline-stages)
  - [Viewing Stats](#viewing-stats)
- [Application Name](#application-name)
  - [Auto-Detection](#auto-detection)
  - [Override](#override)
  - [Config File](#config-file)
  - [Document Layout](#document-layout)

---
## Configuration Sources

ReleasePilot reads configuration from four sources, in descending priority:

1. **CLI options** - always take precedence
2. **Project config file** - `.releasepilot.json`, `.releasepilot.toml`, or `pyproject.toml [tool.releasepilot]`
3. **User-level config file** - `~/.config/releasepilot/config.json`
4. **Built-in defaults** - sensible out-of-the-box values

If no config file exists, the tool works normally using CLI options and defaults.

## Config File

### Search Order

ReleasePilot searches for config files in this order (first match wins):

1. `.releasepilot.json` - project directory (recommended)
2. `releasepilot.json` - project directory
3. `.releasepilot.toml` - project directory
4. `releasepilot.toml` - project directory
5. `pyproject.toml` - under `[tool.releasepilot]`
6. `~/.config/releasepilot/config.json` - user-level defaults

JSON is the recommended format. A JSON Schema is provided at `schema/releasepilot.schema.json`.

### Supported Fields

**JSON format (recommended):**

```json
{
  "$schema": "./schema/releasepilot.schema.json",
  "app_name": "Loudly",
  "audience": "user",
  "format": "markdown",
  "language": "en",
  "branch": "main",
  "title": "Monthly Release",
  "version": "2.0.0",
  "show_authors": true,
  "show_hashes": false,
  "repos": ["./repo1", "./repo2"],
  "output_dir": "release-notes",
  "overwrite": false,
  "export_formats": ["markdown", "pdf"],
  "ci": {
    "enabled": false,
    "artifact_name": "release-notes",
    "fail_on_empty": false,
    "attach_to_release": false
  }
}
```

**TOML format (also supported):**

```toml
# .releasepilot.toml
app_name = "Loudly"
audience = "user"
format = "markdown"
language = "en"
branch = "main"
title = "Monthly Release"
version = "2.0.0"
show_authors = true
show_hashes = false
repos = ["./repo1", "./repo2"]
```

### pyproject.toml Integration

```toml
[tool.releasepilot]
app_name = "Loudly"
audience = "user"
language = "de"
```

### Override Behavior

CLI options override config file values. If a CLI option is left at its default, the config file value is used instead.

### Validation

Config files are validated on load. Invalid values produce warnings (printed to stderr) but do not prevent the tool from running - invalid enum values are ignored and built-in defaults are used instead.

For the complete config schema, allowed values, examples, and troubleshooting, see **[Config Schema Reference](config-schema.md)**.

## CLI Options

### Global Options

| Option       | Default | Description                          |
|-------------|---------|--------------------------------------|
| `--repo`     | `.`     | Path to the git repository           |
| `--from`     | auto    | Start ref (tag, commit, branch). Auto-detects latest tag if omitted |
| `--to`       | `HEAD`  | End ref                              |
| `--source-file` | -   | Path to a JSON file with structured changes. When provided, git is not used |
| `--version`  | -       | Release version label (e.g. `1.2.0`) |
| `--title`    | -       | Custom title phrase (e.g. "Monthly Release", "Q1 Summary") |
| `--app-name` | -       | Application/product name (e.g. "Loudly"). Prepended to the title |
| `--language` | `en`    | Output language code. Translates section headings and labels |
| `--branch`   | -       | Branch to analyze. Used with `--since` for date-range mode |
| `--since`    | -       | Collect commits since this date (`YYYY-MM-DD`). Enables date-range mode |
| `--dry-run`  | off     | Show pipeline summary without rendering output |

### Output Options (generate / export)

| Option           | Default      | Description                            |
|-----------------|--------------|----------------------------------------|
| `--audience`     | `changelog`  | Target audience: `technical`, `user`, `summary`, `changelog`, `executive` |
| `--format`       | `markdown`   | Output format: `markdown`, `plaintext`, `json`, `pdf`, `docx` |
| `--show-authors` | off          | Include author names in rendered output |
| `--show-hashes`  | off          | Include short commit hashes            |
| `-o` / `--output`| required for `export` | Output file path              |

## Optional Dependencies

PDF/DOCX export and translation require extra packages:

```bash
# Install export dependencies only
pip install "releasepilot[export]"

# Install translation support
pip install "releasepilot[translate]"

# Install everything (dev + export + translate)
pip install "releasepilot[all]"
```

| Dependency       | Purpose           | Required for          |
|-----------------|-------------------|-----------------------|
| `reportlab`     | PDF generation    | `--format pdf`        |
| `python-docx`   | DOCX generation   | `--format docx`       |
| `deep-translator`| Content translation | `--language` (non-en) |

If you try to export as PDF or DOCX without these packages, ReleasePilot will tell you exactly how to install them.

## Structured Input Format

When using `--source-file`, provide a JSON file:

```json
{
  "changes": [
    {
      "title": "Required: short change description",
      "description": "Optional: longer description",
      "category": "feature",
      "scope": "auth",
      "authors": ["alice", "bob"],
      "pr_number": 42,
      "issue_numbers": [10, 11],
      "breaking": false,
      "importance": "normal",
      "metadata": {"ticket": "PROJ-123"}
    }
  ]
}
```

### Field Reference

| Field          | Required | Type       | Default  | Description |
|---------------|----------|------------|----------|-------------|
| `title`       | ✅        | string     | -        | Short change description |
| `description` | ❌        | string     | `""`     | Longer description |
| `category`    | ❌        | string     | `"other"`| Change category |
| `scope`       | ❌        | string     | `""`     | Component/area |
| `authors`     | ❌        | string[]   | `[]`     | Author names |
| `pr_number`   | ❌        | int        | null     | Pull request number |
| `issue_numbers`| ❌       | int[]      | `[]`     | Related issue numbers |
| `breaking`    | ❌        | boolean    | `false`  | Is this a breaking change? |
| `importance`  | ❌        | string     | `"normal"`| `high`, `normal`, `low`, `noise` |
| `metadata`    | ❌        | object     | `{}`     | Arbitrary key-value metadata |

### Categories

`feature`, `improvement`, `bugfix`, `performance`, `security`, `breaking`, `deprecation`, `documentation`, `infrastructure`, `refactor`, `other`

## Noise Filtering

The following patterns are filtered by default:

- `Merge branch/pull request/remote...`
- `Revert "Revert...`
- `wip:`, `WIP:`
- `fixup!`, `squash!`
- `chore(deps):`
- `bump version`
- `auto-merge`
- Titles shorter than 4 characters

## Conventional Commits

ReleasePilot parses [Conventional Commits](https://www.conventionalcommits.org/) format:

```
type(scope): description

optional body

BREAKING CHANGE: description
```

Supported types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, `security`, `deprecate`

Breaking changes are detected via the `!` suffix (`feat!:`) or the `BREAKING CHANGE` footer.

## Date-Range Mode

When `--since` is provided, ReleasePilot switches to date-range mode:

- `--from` and `--to` are not required
- Commits are collected from `--since` date to the present on the specified `--branch`
- **Only commits reachable from the selected branch are analyzed** - commits on unrelated branches are excluded
- If `--branch` is omitted, defaults to `HEAD`
- Combine with `--version` to label the release

### Branch Validation

In the guided workflow, branches are validated before proceeding:

- If the entered branch does not exist locally, the workflow **stops and shows available branches**
- The user must provide a valid branch name before the time-range step begins
- Default branch is auto-detected (`main` → `master` → ask user)

```bash
# Last month's changes on main
releasepilot generate --since 2025-02-01 --branch main

# Last month's changes, labeled as v2.0.0
releasepilot generate --since 2025-02-01 --branch main --version 2.0.0
```

### Requested vs Effective Range

If the requested date range extends beyond the repository's first commit, the tool:

1. Detects the first available commit date
2. Warns the user that the requested range exceeds history
3. Adjusts the effective start date to the first commit
4. Clearly shows both the **requested** and **effective** ranges

Example output in guided mode:
```
→ Requested: last 30 days (since 2026-02-14)
→ Effective: since 2026-03-08 (adjusted to first available commit)
```

The tool never pretends the repository has more history than it actually has.

## Guided Workflow

The `guide` command provides an interactive alternative to manual CLI options:

```bash
releasepilot guide [repo_path_or_url]
```

It walks through:
1. Repository resolution (local path or remote URL clone)
2. Repository inspection and validation (with spinner)
3. Changelog/release-notes file detection (with staleness warning)
4. Branch selection with validation - invalid branches are rejected
5. Time range selection (7/14/30/60/90 days, custom date `YYYY-MM-DD`, or number of days back e.g. `30`)
6. Audience selection - default: **Executive / management brief**. Also supports: changelog, user-facing, technical, summary, customer-facing
7. Format selection (executive defaults to PDF)
8. Custom subtitle (repository name is used automatically as the app name)
9. Generation with preview and export (with spinner)
10. Overwrite protection - asks before replacing existing files
11. Cleanup of cloned repos (if applicable)

This is ideal for QA, testers, and non-developer users who may not know exact refs or tags. The guided workflow auto-detects branches, suggests sensible defaults, and explains each step.

### Remote URL support

Pass a GitHub URL directly:

```bash
releasepilot guide https://github.com/user/repo
```

The repository is cloned to a temp directory (shallow, 200 commits), analyzed normally, and you're asked whether to remove it at the end.

### Smart defaults

After repeating the same guided choice 3+ times, it becomes the pre-selected default. This reduces friction for frequent users.

- Stored in `~/.config/releasepilot/preferences.json`
- Reset with `releasepilot guide --reset-preferences`
- Disable with `RELEASEPILOT_NO_PREFS=1`

At the start of each guided session, a short tip explains this behaviour:

```
💡 Tip: Choices you repeat 3+ times become remembered defaults,
   making future runs faster.
   Preferences are stored in ~/.config/releasepilot/preferences.json
   (set RELEASEPILOT_NO_PREFS=1 to disable).
```

### Progress feedback

Spinners are displayed during long-running operations (inspecting, cloning, generating) so users always know the tool is working.

### Interactive navigation

Every menu in the guided workflow supports:

- **Arrow-key navigation** - ↑/↓ to move, Enter to confirm (requires a real terminal)
- **Numeric entry** - type the number and press Enter (works in all environments)

Arrow-key mode is provided by [questionary](https://github.com/tmbo/questionary) and activates automatically when running in a terminal. In non-TTY environments (CI, piped input), validated numeric prompts are used.

### Input validation

All interactive prompts enforce strict validation:

- Only listed option numbers are accepted
- Non-numeric input is rejected with a clear message
- Out-of-range numbers are rejected with the valid range displayed
- Choices are re-displayed after each invalid attempt
- The user stays on the current step until a valid selection is made
- **Branch**: must exist locally; shows available branches on failure
- **Custom date/days**: accepts `YYYY-MM-DD` date or integer days back (e.g. `30`); future dates rejected; must be 1-3650 for days; re-prompts until valid
- **Subtitle**: trimmed of whitespace; capped at 200 characters; blank is allowed (skips subtitle)
- **Filename**: overwrite check with overwrite/rename/cancel options (overwrite is default)

Invalid input never silently falls through to a default.

## Dry-Run Mode

Use `--dry-run` to inspect the pipeline without producing output:

```bash
releasepilot generate --from v1.0.0 --to v1.1.0 --dry-run
releasepilot generate --since 2025-02-01 --branch main --dry-run
```

Dry-run shows:
- Number of changes collected
- Classification breakdown
- Grouping summary
- Audience and format that would be used

This is useful for verifying your inputs before committing to a full generation or export.

## Pre-flight Validation

ReleasePilot validates all inputs before executing the pipeline:

| Check | When | Error |
|-------|------|-------|
| Git repository | Always (unless `--source-file`) | "Not a git repository" with path help |
| Ref exists | When `--from` or `--to` provided | "Tag/ref not found" with list command |
| Date format | When `--since` provided | "Invalid date format" with correct format |
| Source file exists | When `--source-file` provided | "File not found" with path check |
| Export path writable | On `export` command | "Cannot write to path" with parent dir help |
| Export deps installed | When `--format pdf/docx` | "Missing dependency" with install command |

All errors are displayed as structured panels with:
- **Summary** - what went wrong
- **Reason** - why it happened
- **Suggestions** - what to try next
- **Example** - corrected command

## Empty Release Detection

If the pipeline produces no meaningful changes, ReleasePilot provides helpful guidance:

- Suggests widening the date range
- Suggests trying a different branch
- Suggests using `releasepilot guide` for interactive discovery

This avoids confusing "empty output" situations.

## Executive Audience Mode

The `executive` audience produces business-oriented release communication.

### What it does

- Filters out internal-only categories (refactors, infrastructure, docs)
- Strips conventional commit prefixes from titles
- Groups changes into business themes (New Capabilities, Quality & Reliability, etc.)
- Generates a natural-language executive summary
- Extracts key achievements from highlights
- Identifies risks from breaking changes and deprecations
- Produces actionable next-step recommendations

### Document structure

Executive output includes these sections:

| Section | Content |
|---------|---------|
| Executive Summary | 2-4 sentence business overview |
| Key Achievements | Top 3-7 highlights in business language |
| Impact Areas | Changes grouped by business theme with summaries |
| Risks & Attention Items | Breaking changes and deprecations as risks |
| Recommended Next Steps | Actionable follow-up items |
| Release Metrics | Summary statistics table |

### Usage examples

```bash
# Executive brief to stdout
releasepilot generate --source-file changes.json --audience executive --version 3.0.0

# Executive PDF for board review
releasepilot export --source-file changes.json --audience executive --format pdf -o brief.pdf

# Executive DOCX for management
releasepilot export --source-file changes.json --audience executive --format docx -o brief.docx

# Executive JSON for integration
releasepilot generate --source-file changes.json --audience executive --format json
```

### Guided workflow

In the guided workflow (`releasepilot guide`), choosing "Executive / management brief" as the audience automatically recommends PDF or DOCX as the output format.

### Audience comparison

| Audience | Technical detail | Business language | Internal categories | Output structure |
|----------|-----------------|-------------------|--------------------|--------------------|
| `technical` | Full - raw data | No | Included | Standard changelog |
| `changelog` | Full - polished titles | Capitalized | Included | Standard changelog |
| `user` | Moderate - user-relevant | Polished titles | Hidden | Standard changelog |
| `summary` | Minimal - top 3/group | No | Hidden | Standard changelog |
| `executive` | None - business only | Yes | Hidden | Executive brief |

**Key differences:**
- `technical` vs `changelog`: Both include all categories. `changelog` capitalizes and cleans titles; `technical` returns raw data unchanged.
- `user` vs `summary`: Both hide internal categories. `user` shows all user-relevant items; `summary` limits to 3 per group for brevity.
- `executive`: Completely different structure - business themes, impact analysis, risk sections, and next steps instead of a traditional changelog.

### Date-range history bounds

When `--since` specifies a date before the repository's first commit, ReleasePilot detects this and adjusts:

- The effective start date is clamped to the first commit date
- A warning is printed explaining the adjustment
- The final output reflects the actual analysis range, not the requested one

## Title Composition

ReleasePilot composes document titles from multiple inputs:

| Input | CLI Option | Description |
|-------|-----------|-------------|
| App name | `--app-name` | Product/application name (e.g. "Loudly") |
| Custom title | `--title` | Free-text title phrase (e.g. "Monthly Release") |
| Version | `--version` | Version label (e.g. "2.0.0") |

**Composition rules:**
1. If `--app-name` is provided, it appears first, separated by " - "
2. If `--title` is provided, it is used as the title phrase
3. Otherwise, a fallback is generated (e.g. "Changes since 2025-01-01")
4. If `--version` is provided and not already in the phrase, " - Version X.Y.Z" is appended

**Examples:**

```
--app-name "Loudly" --title "Q1 Summary" --version 3.1.0
→ Loudly - Q1 Summary - Version 3.1.0

--app-name "Loudly" --since 2025-01-01
→ Loudly - Changes since 2025-01-01

--title "Board Update"
→ Board Update
```

In the guided workflow, the app name prompt includes a visual preview:

```
📦 Application / product name
This will appear centered at the top of the document, above the release title.
Leave blank to use the repository name automatically.

  Example document layout:
    ┌─────────────────────────┐
    │       Loudly            │
    │  Monthly Release Overview│
    │  Version 2.0.0           │
    └─────────────────────────┘
```

### Document Title Hierarchy

In PDF and DOCX documents, the title block is structured as:

1. **App name** - centered, large (28pt), visually prominent
2. **Title / subtitle** - left-aligned, smaller (22pt in PDF, 20pt in DOCX)
3. **Metadata** - version, date, pipeline summary in smaller italic text

This creates a clear visual hierarchy where the application name is the most prominent element.

## Translation

### Supported languages

| Code | Language   | Label example (Highlights)  |
|------|------------|----------------------------|
| `en` | English    | Highlights                 |
| `pl` | Polish     | Najważniejsze              |
| `de` | German     | Highlights                 |
| `fr` | French     | Points clés                |
| `es` | Spanish    | Aspectos destacados        |
| `it` | Italian    | Punti salienti             |
| `pt` | Portuguese | Destaques                  |
| `nl` | Dutch      | Hoogtepunten               |
| `uk` | Ukrainian  | Основне                    |
| `cs` | Czech      | Hlavní body                |

### What is translated

**Static labels** (built-in dictionaries, no network required):
- Section headings: Highlights, Breaking Changes, etc.
- Metadata text: "Released on {date}", "{count} changes in this release"

**Content translation** (optional, requires `deep-translator`):
- Available via the `translate_text()` function
- Uses Google Translate with placeholder protection
- Preserves version numbers, dates, issue refs, inline code, and bold markdown

### Architecture

The translation system (`src/releasepilot/i18n/`) consists of:

| Module | Purpose |
|--------|---------|
| `labels.py` | Static dictionary of translated UI/structural labels |
| `translator.py` | Optional content translation via `deep-translator` |
| `__init__.py` | Public API: `get_label()`, `get_labels_for()`, `translate_text()` |

### Adding a new language

1. Add the language code to `SUPPORTED_LANGUAGES` in `labels.py`
2. Add translations for each label key in the `_LABELS` dictionary
3. No code changes are needed elsewhere - renderers use `get_label(key, lang)` automatically

## Multi-Repository Generation

Generate release notes from multiple repositories in a single run using the `multi` command.

### Usage

```bash
# Combined output to stdout
releasepilot multi ./repo1 ./repo2 ./repo3 --since 2025-01-01

# Per-repo output files in a directory
releasepilot multi ./repo1 ./repo2 -o ./output/ --format markdown

# With audience and language
releasepilot multi ./repo1 ./repo2 --audience user --language de
```

### Behavior

- Each repository is processed independently
- The repository directory name is used as the application name automatically
- Results are clearly separated per repository
- Errors in one repo do not prevent processing of others
- With `-o`, files are saved as `<repo-name>.md` (or `.txt`, `.json`)
- Without `-o`, combined output is printed to stdout

## Pipeline Transparency

ReleasePilot shows how raw changes are reduced to final release notes so users understand why the output contains the number of entries it does.

### Pipeline Stages

```
Raw changes → Classification → Filtering → Deduplication → Grouping → Audience → Rendering
```

| Stage | What happens |
|-------|-------------|
| Collection | Raw commits/items gathered from source |
| Classification | Each item categorized (feat, fix, docs...) |
| Filtering | Noise removed: merges, WIP, fixups, short messages |
| Deduplication | Exact duplicates, PR grouping, near-duplicate removal |
| Audience | Category hiding + title polishing per audience mode |
| Rendering | Final output in selected format |

### Viewing Stats

Use `--dry-run` or the `analyze` command:

```
  Raw changes:    20
  After filter:   15
  After dedup:    12
  Filtered out:   5
  Dedup removed:  3
  Final:          12
```

The pipeline summary also appears in rendered Markdown footers and PDF/DOCX subtitles.

## Application Name

### Auto-Detection

When `--app-name` is not specified, ReleasePilot uses the repository directory name as the application name. For example, if the repo is at `/home/user/projects/Loudly`, the title becomes:

```
Loudly - Changes since 2025-01-01
```

### Override

```bash
releasepilot generate --app-name "My Product" --since 2025-01-01
```

### Config File

```toml
app_name = "Loudly"
```

### Document Layout

In PDF and DOCX exports, the application name appears prominently at the top (centered, large font) with the rest of the title below it. This creates a clear visual hierarchy:

```
                    Loudly                     ← large, centered
    Changes since 2025-01-01 - Version 2.0    ← normal title
    Released 2025-06-01 · 12 changes           ← metadata
```
