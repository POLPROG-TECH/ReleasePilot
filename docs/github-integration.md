# GitHub Actions Integration


## Table of Contents

- [Quick Start (5 minutes)](#quick-start-5-minutes)
  - [Option A: Copy a minimal workflow](#option-a-copy-a-minimal-workflow)
  - [Option B: Use the full template](#option-b-use-the-full-template)
- [Available Templates](#available-templates)
  - [1. Tag-triggered (recommended)](#1-tag-triggered-recommended)
  - [2. Manual dispatch](#2-manual-dispatch)
  - [3. Scheduled](#3-scheduled)
  - [4. Reusable workflow (for organizations)](#4-reusable-workflow-for-organizations)
- [Setup Checklist](#setup-checklist)
- [Configuration](#configuration)
  - [Workflow-level configuration (env / inputs)](#workflow-level-configuration-env-inputs)
  - [Repository-level configuration (.releasepilot.json)](#repository-level-configuration-releasepilotjson)
- [Attaching Notes to GitHub Releases](#attaching-notes-to-github-releases)
- [Generating Multiple Formats](#generating-multiple-formats)
- [Secrets Required](#secrets-required)
- [Customization](#customization)
  - [Change the Python version](#change-the-python-version)
  - [Install a specific ReleasePilot version](#install-a-specific-releasepilot-version)
  - [Add translation support](#add-translation-support)
  - [Use structured input (no git)](#use-structured-input-no-git)
  - [Generate only for a date range](#generate-only-for-a-date-range)
- [Troubleshooting](#troubleshooting)
  - ["Not a git repository" or missing history](#not-a-git-repository-or-missing-history)
  - [Empty release notes](#empty-release-notes)
  - ["Missing dependency: reportlab"](#missing-dependency-reportlab)
  - [Workflow does not trigger](#workflow-does-not-trigger)
  - [Permission denied on release upload](#permission-denied-on-release-upload)

---
This guide explains how to use ReleasePilot in GitHub Actions to automatically generate release notes.

## Quick Start (5 minutes)

### Option A: Copy a minimal workflow

Copy [`examples/github-workflow.yml`](../examples/github-workflow.yml) to `.github/workflows/release-notes.yml` in your repository:

```yaml
name: Release Notes
on:
  push:
    tags: ["v*"]

jobs:
  notes:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "releasepilot[export] @ git+https://github.com/polprog-tech/ReleasePilot.git@main"
      - run: |
          VERSION="${GITHUB_REF#refs/tags/v}"
          releasepilot export --audience changelog --version "$VERSION" -o RELEASE_NOTES.md
      - uses: actions/upload-artifact@v4
        with:
          name: release-notes
          path: RELEASE_NOTES.md
```

Push a tag and release notes appear as a downloadable artifact.

### Option B: Use the full template

Copy [`templates/github/release-notes.yml`](../templates/github/release-notes.yml) to `.github/workflows/release-notes.yml` for a feature-complete setup with:

- Multi-format output (Markdown + PDF + DOCX)
- Version auto-detection from tags
- Artifact upload
- Optional GitHub Release attachment

## Available Templates

### 1. Tag-triggered (recommended)

**File:** [`.github/workflows/release-notes.yml`](../.github/workflows/release-notes.yml)

**Trigger:** When you push a tag matching `v*`.

**Best for:** Standard versioned releases.

**Configuration:** Edit the `env:` section at the top of the file:

```yaml
env:
  AUDIENCE: "user"
  FORMATS: "markdown,pdf"
  LANGUAGE: "en"
  APP_NAME: ""
  SHOW_AUTHORS: "false"
  SHOW_HASHES: "false"
```

### 2. Manual dispatch

**File:** [`templates/github/release-notes-manual.yml`](../templates/github/release-notes-manual.yml)

**Trigger:** Manual button in GitHub Actions UI (Actions → workflow → "Run workflow").

**Best for:** Ad-hoc generation, testing, retrospective notes.

**How it works:** All parameters are configurable through the "Run workflow" form:

- Audience, format, language (dropdowns)
- Version, from-ref, to-ref, since, branch (text fields)

### 3. Scheduled

**File:** [`templates/github/release-notes-schedule.yml`](../templates/github/release-notes-schedule.yml)

**Trigger:** Cron schedule (default: every Monday at 08:00 UTC) + manual dispatch.

**Best for:** Sprint reports, weekly/monthly stakeholder summaries.

**Configuration:** Edit the `env:` section and cron schedule:

```yaml
on:
  schedule:
    - cron: "0 8 * * 1"    # Every Monday at 08:00 UTC

env:
  AUDIENCE: "executive"
  FORMATS: "markdown,pdf"
  SINCE_DAYS: "14"
  TITLE: "Sprint Report"
```

### 4. Reusable workflow (for organizations)

**File:** [`templates/github/release-notes.yml`](../templates/github/release-notes.yml)

**Trigger:** Called from other workflows via `workflow_call`.

**Best for:** Organizations that want a single, centralized release notes workflow shared across multiple repositories.

**Usage in a consumer workflow:**

```yaml
name: Release
on:
  push:
    tags: ["v*"]

jobs:
  release-notes:
    uses: your-org/shared-workflows/.github/workflows/release-notes.yml@main
    with:
      audience: user
      formats: "markdown,pdf"
      language: en
      show-authors: true
      attach-to-release: true
```

## Setup Checklist

1. ✅ **Copy a template** to `.github/workflows/release-notes.yml`
2. ✅ **Configure** `env:` variables or workflow inputs
3. ✅ **Ensure `fetch-depth: 0`** in the checkout step (critical!)
4. ✅ **(Optional)** Add `.releasepilot.json` to your repo root for shared defaults
5. ✅ **Push a tag** to test: `git tag v0.1.0-test && git push origin v0.1.0-test`
6. ✅ **Check artifacts** in the Actions run

## Configuration

### Workflow-level configuration (env / inputs)

These are set in the workflow file and control pipeline behavior:

| Variable/Input | Description | Default |
|---------------|-------------|---------|
| `audience` | Target audience mode | `changelog` |
| `formats` | Comma-separated output formats | `markdown` |
| `language` | Output language code | `en` |
| `app-name` | Application name | Auto-detect |
| `title` | Custom title phrase | Auto-detect |
| `version` | Version label | Auto-detect from tag |
| `from-ref` | Start ref | Auto-detect (latest tag) |
| `to-ref` | End ref | `HEAD` |
| `since` | Since date (date-range mode) | — |
| `branch` | Branch (date-range mode) | — |
| `show-authors` | Include author names | `false` |
| `show-hashes` | Include commit hashes | `false` |
| `output-dir` | Output directory | `release-notes` |
| `artifact-name` | Upload artifact name | `release-notes` |
| `attach-to-release` | Attach to GitHub Release | `false` |

### Repository-level configuration (.releasepilot.json)

Add a `.releasepilot.json` to your repository root. This serves as the shared default for both local use and CI:

```json
{
  "$schema": "https://raw.githubusercontent.com/polprog-tech/ReleasePilot/main/schema/releasepilot.schema.json",
  "app_name": "MyApp",
  "audience": "user",
  "language": "en",
  "show_authors": true
}
```

CLI flags (set by the workflow) override config file values.

## Attaching Notes to GitHub Releases

To automatically set the body of a GitHub Release:

1. Set `attach-to-release: true` in the reusable workflow, or add this step:

```yaml
- name: Attach to Release
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    TAG="${GITHUB_REF#refs/tags/}"
    gh release edit "$TAG" --notes-file release-notes/RELEASE_NOTES.md
```

2. The `GITHUB_TOKEN` is automatically available — no additional secrets needed.

3. **Important:** The GitHub Release must already exist. If you create releases manually, push the tag first, create the release, then the workflow will update it. Or use `gh release create` in your workflow.

## Generating Multiple Formats

To produce Markdown, PDF, and DOCX in one run:

```yaml
env:
  FORMATS: "markdown,pdf,docx"
```

The templates loop over formats and generate each one. All files are uploaded as a single artifact.

## Secrets Required

| Secret | Provided by | Purpose |
|--------|------------|---------|
| `GITHUB_TOKEN` | Automatic | Attach notes to GitHub Release |

No additional secrets are needed. ReleasePilot reads git history directly from the checked-out repository.

## Customization

### Change the Python version

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.13"    # or "3.12"
```

### Install a specific ReleasePilot version

```yaml
- run: pip install "releasepilot[export] @ git+https://github.com/polprog-tech/ReleasePilot.git@v1.0.0"
```

### Add translation support

```yaml
- run: pip install "releasepilot[export] @ git+https://github.com/polprog-tech/ReleasePilot.git@main" deep-translator
```

### Use structured input (no git)

```yaml
- run: releasepilot export --source-file changes.json --audience user -o RELEASE_NOTES.md
```

### Generate only for a date range

```yaml
- run: releasepilot export --since 2025-01-01 --branch main --audience executive --format pdf -o report.pdf
```

## Troubleshooting

### "Not a git repository" or missing history

**Cause:** `fetch-depth` is not set to `0` (GitHub defaults to shallow clone with depth 1).

**Fix:**
```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0    # REQUIRED — full history
```

### Empty release notes

**Cause:** No commits between the detected tags, or all commits were filtered as noise.

**Debug:**
```yaml
- run: |
    releasepilot generate --dry-run
    releasepilot collect
```

### "Missing dependency: reportlab"

**Cause:** PDF format requested but `[export]` extras not installed.

**Fix:** Install with `releasepilot[export]`:
```yaml
- run: pip install "releasepilot[export] @ git+https://github.com/polprog-tech/ReleasePilot.git@main"
```

### Workflow does not trigger

**Check:**
- Tag matches the pattern (e.g. `v*` matches `v1.0.0` but not `1.0.0`)
- Workflow file is on the default branch
- GitHub Actions is enabled for the repository

### Permission denied on release upload

**Cause:** `GITHUB_TOKEN` needs write access to releases.

**Fix:** Ensure the workflow has `contents: write` permission:
```yaml
jobs:
  release-notes:
    permissions:
      contents: write
```
