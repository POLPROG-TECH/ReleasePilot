# CI/CD Integration Guide


## Table of Contents

- [Overview](#overview)
- [Platform Guides](#platform-guides)
- [Quick Start](#quick-start)
  - [1. Add a config file (optional but recommended)](#1-add-a-config-file-optional-but-recommended)
  - [2. Copy a workflow template](#2-copy-a-workflow-template)
  - [3. Push a tag](#3-push-a-tag)
- [Template Inventory](#template-inventory)
  - [GitHub Actions](#github-actions)
  - [GitLab CI](#gitlab-ci)
  - [Examples (copy-paste ready)](#examples-copy-paste-ready)
- [Configuration](#configuration)
  - [Config file vs. pipeline variables](#config-file-vs-pipeline-variables)
  - [CI-specific config fields](#ci-specific-config-fields)
  - [Additional config fields for CI](#additional-config-fields-for-ci)
- [When to Generate Release Notes](#when-to-generate-release-notes)
  - [Recommended triggers](#recommended-triggers)
  - [Anti-patterns to avoid](#anti-patterns-to-avoid)
- [Commands for CI](#commands-for-ci)
- [Output Artifacts](#output-artifacts)
  - [File naming](#file-naming)
  - [Multiple formats](#multiple-formats)
- [Secrets and Variables](#secrets-and-variables)
- [Local Validation Before CI](#local-validation-before-ci)
- [Troubleshooting](#troubleshooting)
  - [Common CI issues](#common-ci-issues)
  - [Debugging in CI](#debugging-in-ci)
- [Architecture Diagram](#architecture-diagram)

---
ReleasePilot is designed to work seamlessly in CI/CD pipelines. This guide covers the overall approach, best practices, and links to platform-specific guides.

## Overview

ReleasePilot's CLI commands work identically in CI as they do locally. The key difference is that CI environments are non-interactive, so you use the `export` command (not `guide`) and pass all options via CLI flags or a `.releasepilot.json` config file.

```
releasepilot export --audience user --format markdown --version 1.2.0 -o RELEASE_NOTES.md
```

## Platform Guides

| Platform | Guide | Templates |
|----------|-------|-----------|
| **GitHub Actions** | [GitHub Integration](github-integration.md) | [`templates/github/`](../templates/github/) |
| **GitLab CI** | [GitLab Integration](gitlab-integration.md) | [`templates/gitlab/`](../templates/gitlab/) |

## Quick Start

### 1. Add a config file (optional but recommended)

Create `.releasepilot.json` in your repository root:

```json
{
  "$schema": "https://raw.githubusercontent.com/polprog-tech/ReleasePilot/main/schema/releasepilot.schema.json",
  "app_name": "MyApp",
  "audience": "user",
  "language": "en",
  "show_authors": true,
  "ci": {
    "enabled": true,
    "attach_to_release": true
  }
}
```

### 2. Copy a workflow template

**GitHub:** Copy [`templates/github/release-notes.yml`](../templates/github/release-notes.yml) to `.github/workflows/release-notes.yml`.

**GitLab:** Copy [`templates/gitlab/release-notes.gitlab-ci.yml`](../templates/gitlab/release-notes.gitlab-ci.yml) to your repo, then include it from `.gitlab-ci.yml`.

### 3. Push a tag

```bash
git tag v1.2.0
git push origin v1.2.0
```

Release notes are generated automatically.

## Template Inventory

### GitHub Actions

| Template | Purpose | Trigger |
|----------|---------|---------|
| [`release-notes.yml`](../templates/github/release-notes.yml) | Reusable workflow (call from other workflows) | `workflow_call` |
| [`release-notes-manual.yml`](../templates/github/release-notes-manual.yml) | Manual trigger from Actions UI | `workflow_dispatch` |
| [`release-notes-schedule.yml`](../templates/github/release-notes-schedule.yml) | Scheduled generation (weekly, monthly) | `schedule` + `workflow_dispatch` |

### GitLab CI

| Template | Purpose | Trigger |
|----------|---------|---------|
| [`release-notes.gitlab-ci.yml`](../templates/gitlab/release-notes.gitlab-ci.yml) | Reusable include (extend `.releasepilot` job) | Depends on consumer |
| [`release-notes-manual.gitlab-ci.yml`](../templates/gitlab/release-notes-manual.gitlab-ci.yml) | Manual trigger from pipeline UI | `when: manual` |
| [`release-notes-schedule.gitlab-ci.yml`](../templates/gitlab/release-notes-schedule.gitlab-ci.yml) | Scheduled generation | Pipeline schedules |

### Examples (copy-paste ready)

| File | Description |
|------|-------------|
| [`examples/github-release-notes.yml`](../examples/github-release-notes.yml) | GitHub Actions workflow for release notes |
| [`examples/gitlab-release-notes.yml`](../examples/gitlab-release-notes.yml) | GitLab CI job for release notes |
| [`examples/.releasepilot.json`](../examples/.releasepilot.json) | Example config with CI settings |
| [`examples/multi-repo-config.json`](../examples/multi-repo-config.json) | Multi-repository config example |
| [`examples/cli-usage.sh`](../examples/cli-usage.sh) | CLI usage examples |
| [`examples/remote-repos.md`](../examples/remote-repos.md) | Remote/multi-repo dashboard guide |

## Configuration

### Config file vs. pipeline variables

ReleasePilot supports two complementary configuration approaches in CI:

| Approach | When to use |
|----------|-------------|
| **`.releasepilot.json`** | Project-level defaults shared across all pipelines and local usage |
| **Pipeline variables / inputs** | Per-run overrides (manual triggers, environment-specific values) |

CLI flags (from pipeline variables) always override config file values:

```
Final value = CLI flag > .releasepilot.json > built-in default
```

### CI-specific config fields

The `ci` section in `.releasepilot.json` controls CI behavior:

```json
{
  "ci": {
    "enabled": true,
    "artifact_name": "release-notes",
    "fail_on_empty": false,
    "attach_to_release": true
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ci.enabled` | boolean | `false` | Enables CI mode (non-interactive, overwrite-safe) |
| `ci.artifact_name` | string | `"release-notes"` | Label for CI artifacts |
| `ci.fail_on_empty` | boolean | `false` | Exit non-zero if no changes found |
| `ci.attach_to_release` | boolean | `false` | Hint for templates to attach notes to a release |

### Additional config fields for CI

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_dir` | string | `""` | Directory for generated files |
| `overwrite` | boolean | `false` | Overwrite existing files without prompting |
| `export_formats` | list | `[]` | Multiple formats to generate in one run |

For the full config reference, see [Configuration](configuration.md) and [Config Schema](config-schema.md).

## When to Generate Release Notes

### Recommended triggers

| Trigger | Use case | Recommendation |
|---------|----------|----------------|
| **Tag push** (`v*`) | Versioned releases | ✅ **Best for most teams.** Generates notes for the exact release. |
| **Manual dispatch** | Ad-hoc generation, testing | ✅ Good for flexibility. Use workflow inputs for parameters. |
| **Schedule** (weekly/monthly) | Sprint reports, stakeholder updates | ✅ Good for recurring reports. Use `--since` with date-range mode. |
| **Push to main** | Continuous delivery | ⚠️ Use with caution — can be noisy. Consider `--dry-run` first. |
| **Pull request** | Preview notes before merge | ⚠️ Use `preview` or `--dry-run`, not `export`. Avoid artifact spam. |

### Anti-patterns to avoid

| Anti-pattern | Why it's bad | What to do instead |
|--------------|-------------|-------------------|
| Generate on every push to every branch | Noisy, wastes CI minutes | Trigger only on tags or main branch |
| Generate without `fetch-depth: 0` | Missing git history = wrong output | Always use full clone |
| Hardcode version in pipeline | Drifts from actual release | Auto-detect from tag (`${GITHUB_REF#refs/tags/v}`) |
| Skip config file, pass everything via env vars | Hard to maintain, inconsistent with local usage | Use `.releasepilot.json` for defaults |
| Generate in PR and commit the output | Merge conflicts, stale artifacts | Generate in release pipeline, upload as artifacts |

## Commands for CI

| Command | Purpose | CI usage |
|---------|---------|----------|
| `releasepilot export -o FILE` | Generate and write to file | ✅ Primary CI command |
| `releasepilot generate` | Generate and print to stdout | ✅ Good for piping to other tools |
| `releasepilot generate --dry-run` | Show pipeline summary | ✅ Good for PR checks |
| `releasepilot analyze` | Show classification details | ✅ Good for debugging |
| `releasepilot collect` | Show raw collected changes | ✅ Good for debugging |
| `releasepilot guide` | Interactive workflow | ❌ Not for CI (requires TTY) |

## Output Artifacts

### File naming

ReleasePilot generates files with predictable names:

| Format | Default file | Audience: executive |
|--------|-------------|---------------------|
| Markdown | `RELEASE_NOTES.md` | `RELEASE_BRIEF.md` |
| Plain text | `RELEASE_NOTES.txt` | `RELEASE_BRIEF.txt` |
| JSON | `RELEASE_NOTES.json` | `RELEASE_BRIEF.json` |
| PDF | `RELEASE_NOTES.pdf` | `RELEASE_BRIEF.pdf` |
| DOCX | `RELEASE_NOTES.docx` | `RELEASE_BRIEF.docx` |

When using the `export` command with `-o`, you control the exact file name.

### Multiple formats

To generate multiple formats in one pipeline run, loop over formats:

```bash
for fmt in markdown pdf; do
  releasepilot export --audience user --format "$fmt" -o "release-notes/RELEASE_NOTES.${fmt}"
done
```

The provided templates handle this automatically via the `formats` input.

## Secrets and Variables

ReleasePilot itself requires **no secrets or API tokens**. It reads directly from the git repository.

However, some CI features may require tokens:

| Feature | Required token | Platform |
|---------|---------------|----------|
| Attach notes to GitHub Release | `GITHUB_TOKEN` (auto-provided) | GitHub Actions |
| Upload to GitLab Release | `CI_JOB_TOKEN` (auto-provided) | GitLab CI |
| Translation (`--language` with `deep-translator`) | None (uses free translation APIs) | Both |

## Local Validation Before CI

Before pushing to CI, validate your setup locally:

```bash
# Verify the config file is valid
releasepilot generate --dry-run

# Preview output without writing files
releasepilot preview --audience user

# Test the exact export command your CI will run
releasepilot export --audience user --format markdown --version 1.0.0 -o /tmp/test-notes.md
```

## Troubleshooting

### Common CI issues

| Issue | Cause | Fix |
|-------|-------|-----|
| "Not a git repository" | Shallow clone or missing checkout | Set `fetch-depth: 0` (GitHub) or `GIT_DEPTH: 0` (GitLab) |
| "Tag/ref not found" | Shallow clone missing tags | Use `fetch-depth: 0` for full history |
| Empty output | No commits in the ref range | Verify `--from`/`--to` or `--since` values. Use `collect` to debug |
| "Missing dependency: reportlab" | PDF export without extras | Install with `pip install "releasepilot[export]"` |
| "Missing dependency: python-docx" | DOCX export without extras | Install with `pip install "releasepilot[export]"` |
| Permission denied writing file | Output path not writable | Ensure `mkdir -p` before writing |
| Config warnings in CI logs | Invalid `.releasepilot.json` values | Check config against the schema |

### Debugging in CI

Add these steps to diagnose issues:

```bash
# Show ReleasePilot version
releasepilot --version

# Show what would be generated (without generating)
releasepilot generate --dry-run

# Show raw collected changes
releasepilot collect

# Show classification analysis
releasepilot analyze
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    CI/CD Pipeline                        │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ Checkout  │──▶│   Install    │──▶│   releasepilot │  │
│  │ (full)    │   │ ReleasePilot │   │     export     │  │
│  └──────────┘   └──────────────┘   └───────┬────────┘  │
│                                             │           │
│                       ┌─────────────────────┼───────┐   │
│                       │                     ▼       │   │
│                       │  .releasepilot.json         │   │
│                       │  (config defaults)          │   │
│                       └─────────────────────────────┘   │
│                                             │           │
│                              ┌──────────────┼───────┐   │
│                              │   Artifacts  ▼       │   │
│                              │  ├─ RELEASE_NOTES.md │   │
│                              │  ├─ RELEASE_NOTES.pdf│   │
│                              │  └─ RELEASE_NOTES... │   │
│                              └──────────────────────┘   │
│                                             │           │
│                              ┌──────────────▼───────┐   │
│                              │  Upload / Publish    │   │
│                              │  (artifact, release) │   │
│                              └──────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```
