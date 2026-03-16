# ReleasePilot Playground

A complete demo environment for testing all major ReleasePilot workflows end-to-end.

> **Note:** All commands below assume you run them from the **repository root** (`ReleasePilot/`), not from the `playground/` directory.

## Quick Start

```bash
# 1. Set up sample repositories (creates 7 repos in playground/repos/)
python3 playground/scripts/setup_repos.py

# 2. Run all demos (29 workflows)
python3 playground/scripts/run_demo.py

# 3. Outputs are written to playground/output/
```

## One-Command Demo

```bash
python3 playground/scripts/run_demo.py --setup   # setup + run in one step
```

## Sample Repositories

| Repository | Description | Features |
|---|---|---|
| **acme-web** | Web application | Tags (v2.9.0, v2.10.0, v3.0.0-rc.1), mixed commit types, 85-day history |
| **nova-api** | API microservice | Conventional commits, no tags, 60-day history |
| **orbit-mobile** | Mobile app | Pre-existing CHANGELOG.md |
| **pulse-cli** | CLI tool | Security fixes (`security:`), breaking changes (`feat!:`) |
| **spark-saas** | SaaS platform | Large feature set, ideal for executive/customer demos, 88-day history |
| **atlas-multi-a** | User microservice | Multi-repository demo (part A) |
| **atlas-multi-b** | Order microservice | Multi-repository demo (part B) |

## Demo Groups

Run a specific group with `--only`:

```bash
python3 playground/scripts/run_demo.py --only executive
python3 playground/scripts/run_demo.py --only translation
```

| Group | Demos | Description |
|---|---|---|
| `standard` | 7 | All audience types: changelog, technical, user-facing, summary, customer-style |
| `executive` | 4 | Executive briefs in Markdown, PDF, DOCX, JSON |
| `translation` | 5 | Polish, German, French, Czech translations |
| `formats` | 5 | Markdown, plaintext, JSON, PDF, DOCX |
| `multi` | 1 | Multi-repository combined changelog |
| `daterange` | 4 | 7/30/90-day ranges + tag-based range |
| `config` | 3 | Config-inspired parameter combinations |

## Directory Structure

```
playground/
├── README.md              ← This file
├── .gitignore             ← Ignores repos/ and output/ (generated)
├── scripts/
│   ├── setup_repos.py     ← Creates 7 sample git repositories
│   └── run_demo.py        ← Runs 29 demo workflows
├── configs/               ← Sample configuration files
│   ├── executive-english.json
│   ├── executive-polish.json
│   ├── customer-facing.json
│   ├── technical-detailed.json
│   ├── user-german.json
│   └── multi-repo.json
├── expected/              ← Golden reference outputs (committed)
│   ├── acme-web-changelog.md
│   ├── spark-saas-brief.md
│   ├── acme-web-user-de.md
│   ├── acme-web-tag-range.md
│   └── nova-api-summary.md
├── repos/                 ← Generated sample repos (git-ignored)
└── output/                ← Demo outputs (git-ignored)
    ├── standard/
    ├── executive/
    ├── translation/
    ├── formats/
    ├── daterange/
    ├── config/
    └── multi/
```

## Config Files

The `configs/` directory contains example `.releasepilot.json` files for different scenarios:

| Config | Audience | Format | Language | Notes |
|---|---|---|---|---|
| executive-english.json | executive | pdf | en | Management brief with PDF export |
| executive-polish.json | executive | pdf | pl | Translated executive brief |
| customer-facing.json | user | markdown | en | Customer/user-facing release notes |
| technical-detailed.json | technical | markdown | en | With authors and commit hashes |
| user-german.json | user | markdown | de | German-translated user notes |
| multi-repo.json | changelog | markdown | en | Multi-repository aggregation |

## Expected Outputs

The `expected/` directory contains golden reference outputs. After running the demos, you can compare:

```bash
diff playground/expected/acme-web-changelog.md playground/output/standard/acme-web-changelog.md
```

> **Note:** Outputs contain dates relative to today, so exact diffs may vary. Compare structure and content, not dates.

## Workflows Covered

- ✅ Standard changelog generation
- ✅ Technical / engineering notes
- ✅ User-facing / What's New
- ✅ Concise summary
- ✅ Executive / management brief
- ✅ Customer-facing notes
- ✅ Markdown export
- ✅ PDF export
- ✅ DOCX export
- ✅ JSON export
- ✅ Plaintext export
- ✅ Translated output (Polish, German, French, Czech)
- ✅ Branch selection
- ✅ Date-range input (7/30/90 days)
- ✅ Tag-based range
- ✅ Multi-repository mode
- ✅ Source file (JSON) input
- ✅ Overwrite behavior
