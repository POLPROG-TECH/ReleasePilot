# GitLab CI Integration


## Table of Contents

- [Quick Start (5 minutes)](#quick-start-5-minutes)
  - [Option A: Add a minimal job](#option-a-add-a-minimal-job)
  - [Option B: Use the reusable template](#option-b-use-the-reusable-template)
- [Available Templates](#available-templates)
  - [1. Reusable include (recommended for teams)](#1-reusable-include-recommended-for-teams)
  - [2. Manual trigger](#2-manual-trigger)
  - [3. Scheduled](#3-scheduled)
- [Setup Checklist](#setup-checklist)
- [Configuration](#configuration)
  - [Pipeline variables (RP_*)](#pipeline-variables-rp_)
  - [Repository-level configuration (.releasepilot.json)](#repository-level-configuration-releasepilotjson)
- [Including Templates](#including-templates)
  - [Remote include (simplest)](#remote-include-simplest)
  - [Local include (copy template to your repo)](#local-include-copy-template-to-your-repo)
  - [Project include (from a shared repo in your GitLab instance)](#project-include-from-a-shared-repo-in-your-gitlab-instance)
- [Attaching Notes to GitLab Releases](#attaching-notes-to-gitlab-releases)
- [Generating Multiple Formats](#generating-multiple-formats)
- [Secrets Required](#secrets-required)
- [Customization](#customization)
  - [Use a specific Python version](#use-a-specific-python-version)
  - [Install a specific ReleasePilot version](#install-a-specific-releasepilot-version)
  - [Use structured input (no git)](#use-structured-input-no-git)
  - [Generate only for a date range](#generate-only-for-a-date-range)
- [Troubleshooting](#troubleshooting)
  - ["Not a git repository" or missing history](#not-a-git-repository-or-missing-history)
  - [Empty release notes](#empty-release-notes)
  - ["Missing dependency: reportlab"](#missing-dependency-reportlab)
  - [Job not triggered on tag](#job-not-triggered-on-tag)
  - [Artifacts not visible](#artifacts-not-visible)
  - [Pipeline schedule not working](#pipeline-schedule-not-working)

---
This guide explains how to use ReleasePilot in GitLab CI/CD pipelines to automatically generate release notes.

## Quick Start (5 minutes)

### Option A: Add a minimal job

Add this job to your `.gitlab-ci.yml`:

```yaml
stages:
  - release

release-notes:
  stage: release
  image: python:3.12-slim
  variables:
    GIT_DEPTH: 0
  rules:
    - if: $CI_COMMIT_TAG
  script:
    - pip install --quiet "releasepilot[export] @ git+https://github.com/polprog-tech/ReleasePilot.git@main"
    - |
      VERSION="${CI_COMMIT_TAG#v}"
      releasepilot export --audience changelog --version "$VERSION" -o RELEASE_NOTES.md
  artifacts:
    paths:
      - RELEASE_NOTES.md
    expire_in: 30 days
```

Push a tag and release notes appear as a downloadable artifact.

### Option B: Use the reusable template

Include the reusable template and extend it:

```yaml
include:
  - remote: 'https://raw.githubusercontent.com/polprog-tech/ReleasePilot/main/templates/gitlab/release-notes.gitlab-ci.yml'

stages:
  - release

release-notes:
  extends: .releasepilot
  rules:
    - if: $CI_COMMIT_TAG
  variables:
    RP_AUDIENCE: "user"
    RP_FORMATS: "markdown,pdf"
    RP_LANGUAGE: "en"
```

## Available Templates

### 1. Reusable include (recommended for teams)

**File:** [`templates/gitlab/release-notes.gitlab-ci.yml`](../templates/gitlab/release-notes.gitlab-ci.yml)

**How to use:** Include it and extend the `.releasepilot` hidden job.

**Configuration:** Override `RP_*` variables:

```yaml
include:
  - remote: 'https://raw.githubusercontent.com/polprog-tech/ReleasePilot/main/templates/gitlab/release-notes.gitlab-ci.yml'

release-notes:
  extends: .releasepilot
  rules:
    - if: $CI_COMMIT_TAG
  variables:
    RP_AUDIENCE: "user"
    RP_FORMATS: "markdown,pdf"
    RP_LANGUAGE: "en"
    RP_SHOW_AUTHORS: "true"
```

### 2. Manual trigger

**File:** [`templates/gitlab/release-notes-manual.gitlab-ci.yml`](../templates/gitlab/release-notes-manual.gitlab-ci.yml)

**Trigger:** Manual button in GitLab pipeline UI, or by setting pipeline variables.

**Best for:** Ad-hoc generation, testing, retrospective notes.

**How to run:**
1. Go to CI/CD → Pipelines → Run pipeline
2. Set variables like `RP_AUDIENCE`, `RP_FORMATS`, `RP_VERSION` in the form
3. Click "Run pipeline"

### 3. Scheduled

**File:** [`templates/gitlab/release-notes-schedule.gitlab-ci.yml`](../templates/gitlab/release-notes-schedule.gitlab-ci.yml)

**Trigger:** Pipeline schedule (configured in GitLab UI).

**Best for:** Sprint reports, weekly/monthly stakeholder summaries.

**Setup:**
1. Include or copy the template
2. Go to CI/CD → Schedules → New schedule
3. Set the cron interval (e.g. `0 8 * * 1` for weekly Monday)
4. Add variable `RP_SCHEDULE_RUN = true`

**Configuration:**

```yaml
release-notes:scheduled:
  variables:
    RP_AUDIENCE: "executive"
    RP_FORMATS: "markdown,pdf"
    RP_SINCE_DAYS: "14"
    RP_TITLE: "Sprint Report"
```

## Setup Checklist

1. ✅ **Add the job** to your `.gitlab-ci.yml` (copy or include)
2. ✅ **Set `GIT_DEPTH: 0`** in the job variables (critical!)
3. ✅ **Configure** `RP_*` variables for your project
4. ✅ **(Optional)** Add `.releasepilot.json` to your repo root for shared defaults
5. ✅ **Push a tag** to test: `git tag v0.1.0-test && git push origin v0.1.0-test`
6. ✅ **Download artifacts** from the pipeline's job page

## Configuration

### Pipeline variables (RP_*)

All templates use `RP_*` prefixed variables for configuration. Override them in your job or pipeline UI:

| Variable | Description | Default |
|----------|-------------|---------|
| `RP_AUDIENCE` | Target audience mode | `changelog` |
| `RP_FORMATS` | Comma-separated output formats | `markdown` |
| `RP_LANGUAGE` | Output language code | `en` |
| `RP_APP_NAME` | Application name | Auto-detect |
| `RP_TITLE` | Custom title phrase | Auto-detect |
| `RP_VERSION` | Version label | Auto-detect from `CI_COMMIT_TAG` |
| `RP_FROM_REF` | Start ref | Auto-detect (latest tag) |
| `RP_TO_REF` | End ref | `HEAD` |
| `RP_SINCE` | Since date (YYYY-MM-DD) | — |
| `RP_BRANCH` | Branch (date-range mode) | — |
| `RP_SHOW_AUTHORS` | Include author names | `false` |
| `RP_SHOW_HASHES` | Include commit hashes | `false` |
| `RP_OUTPUT_DIR` | Output directory | `release-notes` |
| `RP_SOURCE_FILE` | Structured JSON input file | — |
| `RP_INSTALL_SPEC` | Pip install specifier | ReleasePilot from GitHub |
| `RP_PYTHON_VERSION` | Python Docker image version | `3.12` |

### Repository-level configuration (.releasepilot.json)

Same as GitHub — add a `.releasepilot.json` to your repository root for shared defaults. Pipeline variables override config file values.

## Including Templates

GitLab CI supports multiple include strategies:

### Remote include (simplest)

```yaml
include:
  - remote: 'https://raw.githubusercontent.com/polprog-tech/ReleasePilot/main/templates/gitlab/release-notes.gitlab-ci.yml'
```

### Local include (copy template to your repo)

```yaml
include:
  - local: 'ci/release-notes.gitlab-ci.yml'
```

### Project include (from a shared repo in your GitLab instance)

```yaml
include:
  - project: 'devops/shared-ci-templates'
    ref: main
    file: '/releasepilot/release-notes.gitlab-ci.yml'
```

## Attaching Notes to GitLab Releases

To create a GitLab Release with the generated notes:

```yaml
release-notes:
  extends: .releasepilot
  rules:
    - if: $CI_COMMIT_TAG
  variables:
    RP_AUDIENCE: "user"
    RP_FORMATS: "markdown"

publish-release:
  stage: release
  image: registry.gitlab.com/gitlab-org/release-cli:latest
  needs: ["release-notes"]
  rules:
    - if: $CI_COMMIT_TAG
  script:
    - echo "Publishing release ${CI_COMMIT_TAG}"
  release:
    tag_name: $CI_COMMIT_TAG
    description: './release-notes/RELEASE_NOTES.md'
    assets:
      links:
        - name: "Release Notes (PDF)"
          url: "${CI_PROJECT_URL}/-/jobs/${CI_JOB_ID}/artifacts/file/release-notes/RELEASE_NOTES.pdf"
```

## Generating Multiple Formats

Set the `RP_FORMATS` variable to a comma-separated list:

```yaml
variables:
  RP_FORMATS: "markdown,pdf,docx"
```

All formats are generated in the same job and stored in the `RP_OUTPUT_DIR` directory.

## Secrets Required

| Token | Provided by | Purpose |
|-------|------------|---------|
| `CI_JOB_TOKEN` | Automatic | Clone repositories, download artifacts |

No additional secrets or tokens are needed. ReleasePilot reads git history from the checked-out repository.

## Customization

### Use a specific Python version

```yaml
variables:
  RP_PYTHON_VERSION: "3.13"
```

### Install a specific ReleasePilot version

```yaml
variables:
  RP_INSTALL_SPEC: "releasepilot[export] @ git+https://github.com/polprog-tech/ReleasePilot.git@v1.0.0"
```

### Use structured input (no git)

```yaml
variables:
  RP_SOURCE_FILE: "changes.json"
```

### Generate only for a date range

```yaml
variables:
  RP_SINCE: "2025-01-01"
  RP_BRANCH: "main"
  RP_AUDIENCE: "executive"
  RP_FORMATS: "pdf"
```

## Troubleshooting

### "Not a git repository" or missing history

**Cause:** `GIT_DEPTH` is not set to `0` (GitLab defaults to depth 20).

**Fix:**
```yaml
variables:
  GIT_DEPTH: 0
```

### Empty release notes

**Cause:** No commits between the detected tags, or all commits filtered.

**Debug:** Add to the script:
```yaml
script:
  - releasepilot generate --dry-run
  - releasepilot collect
```

### "Missing dependency: reportlab"

**Cause:** PDF requested without `[export]` extras.

**Fix:** Ensure the install spec includes `[export]`:
```yaml
variables:
  RP_INSTALL_SPEC: "releasepilot[export] @ git+https://github.com/polprog-tech/ReleasePilot.git@main"
```

### Job not triggered on tag

**Check:**
- The `rules:` section includes `if: $CI_COMMIT_TAG`
- The pipeline is not blocked by other rules
- The `stages:` definition includes `release`

### Artifacts not visible

**Check:**
- The `artifacts:` section lists the correct path
- `expire_in` is set to a reasonable duration
- The job completed successfully (artifacts are not uploaded on failure by default — add `when: always` to `artifacts:` if needed)

### Pipeline schedule not working

**Check:**
- Schedule is active in CI/CD → Schedules
- The variable `RP_SCHEDULE_RUN` is set to `true`
- The owner of the schedule has permission to trigger pipelines
- The pipeline file is on the correct branch
