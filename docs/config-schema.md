# Configuration Schema Reference


## Table of Contents

- [Config File Search Order](#config-file-search-order)
- [Allowed Fields](#allowed-fields)
  - [`ci` Object](#ci-object)
- [Valid Values](#valid-values)
  - [`audience`](#audience)
  - [`format`](#format)
  - [`language`](#language)
- [Override Rules](#override-rules)
- [Examples](#examples)
  - [Minimal config (JSON, recommended)](#minimal-config-json-recommended)
  - [Minimal config (TOML)](#minimal-config-toml)
  - [Standard config](#standard-config)
  - [Executive defaults](#executive-defaults)
  - [Multi-repository config](#multi-repository-config)
  - [User-level config](#user-level-config)
  - [Via pyproject.toml](#via-pyprojecttoml)
  - [CI/CD-ready config](#cicd-ready-config)
- [Invalid Config Examples](#invalid-config-examples)
  - [Unknown key](#unknown-key)
  - [Invalid audience value](#invalid-audience-value)
  - [Wrong type](#wrong-type)
- [Validation Behaviour](#validation-behaviour)
- [What Cannot Be Configured via File](#what-cannot-be-configured-via-file)
- [Resetting / Disabling](#resetting-disabling)

---
ReleasePilot supports project-level configuration via **JSON** (recommended) or TOML files.
A JSON Schema is provided at `schema/releasepilot.schema.json` for editor autocompletion and validation.
CLI arguments always override config-file values.

---

## Config File Search Order

ReleasePilot looks for configuration in this order (first match wins):

1. `.releasepilot.json` — project directory **(recommended)**
2. `releasepilot.json` — project directory
3. `.releasepilot.toml` — project directory
4. `releasepilot.toml` — project directory
5. `pyproject.toml` — under the `[tool.releasepilot]` section
6. `~/.config/releasepilot/config.json` — user-level defaults

If no config file is found, the tool falls back to CLI arguments and guided prompts.

---

## Allowed Fields

| Field           | Type     | Required | Default      | Description                                  |
|-----------------|----------|----------|--------------|----------------------------------------------|
| `app_name`      | string   | No       | *(repo name)*| Application/product name for document title   |
| `audience`      | string   | No       | `changelog`  | Target audience mode                          |
| `format`        | string   | No       | `markdown`   | Output format                                 |
| `language`      | string   | No       | `en`         | Output language code                          |
| `branch`        | string   | No       | *(auto)*     | Git branch to analyse                         |
| `title`         | string   | No       | *(auto)*     | Custom title phrase                           |
| `version`       | string   | No       | *(empty)*    | Release version label (e.g. `2.1.0`)          |
| `show_authors`  | boolean  | No       | `false`      | Show commit authors in output                 |
| `show_hashes`   | boolean  | No       | `false`      | Show commit hashes in output                  |
| `repos`         | list     | No       | `[]`         | Repository paths for multi-repo mode          |
| `output_dir`    | string   | No       | `""`         | Directory for generated output files          |
| `overwrite`     | boolean  | No       | `false`      | Overwrite existing files without prompting     |
| `export_formats`| list     | No       | `[]`         | Multiple output formats for CI (e.g. `["markdown", "pdf"]`) |
| `ci`            | object   | No       | *(see below)*| CI/CD-specific configuration                  |

### `ci` Object

| Field              | Type    | Default          | Description                                      |
|--------------------|---------|------------------|--------------------------------------------------|
| `ci.enabled`       | boolean | `false`          | Enable CI mode (non-interactive, overwrite-safe)  |
| `ci.artifact_name` | string  | `"release-notes"`| Name for CI artifacts                            |
| `ci.fail_on_empty` | boolean | `false`          | Exit non-zero if no meaningful changes found      |
| `ci.attach_to_release` | boolean | `false`      | Hint for CI templates to attach notes to a release |

> **Note:** Both `snake_case` and `kebab-case` keys are accepted (e.g. `app_name` or `app-name`).

---

## Valid Values

### `audience`

| Value        | Description                                  |
|--------------|----------------------------------------------|
| `changelog`  | Standard changelog (default)                 |
| `user`       | User-facing / What's New                     |
| `technical`  | Technical / engineering notes                |
| `summary`    | Concise summary                              |
| `customer`   | Customer-facing product update               |
| `executive`  | Executive / management brief                 |

### `format`

| Value       | Description                                   |
|-------------|-----------------------------------------------|
| `markdown`  | Markdown output (default)                     |
| `plaintext` | Plain text                                    |
| `json`      | JSON structured output                        |
| `pdf`       | PDF document (requires `reportlab`)           |
| `docx`      | Word document (requires `python-docx`)        |

### `language`

| Code | Language                    |
|------|-----------------------------|
| `en` | English (default)           |
| `pl` | Polish / Polski             |
| `de` | German / Deutsch            |
| `fr` | French / Français           |
| `es` | Spanish / Español           |
| `it` | Italian / Italiano          |
| `pt` | Portuguese / Português      |
| `nl` | Dutch / Nederlands          |
| `uk` | Ukrainian / Українська      |
| `cs` | Czech / Čeština             |

---

## Override Rules

Config-file values are used as defaults. CLI arguments always take precedence:

```
Final value = CLI argument > Config file > Built-in default
```

| Scenario                         | Behaviour                                  |
|----------------------------------|--------------------------------------------|
| CLI provides `--audience user`   | Uses `user`, ignores config `audience`     |
| Config has `audience = "user"`   | Uses `user` (CLI default is `changelog`)   |
| Neither specified                | Uses built-in default `changelog`          |

The guided workflow (`releasepilot guide`) still asks interactively even when config values exist —
config values are applied when using non-interactive CLI commands.

---

## Examples

### Minimal config (JSON, recommended)

```json
{
  "$schema": "./schema/releasepilot.schema.json",
  "app_name": "Loudly"
}
```

### Minimal config (TOML)

```toml
# .releasepilot.toml
app_name = "Loudly"
```

### Standard config

```json
{
  "$schema": "./schema/releasepilot.schema.json",
  "app_name": "Loudly",
  "audience": "user",
  "format": "markdown",
  "language": "en",
  "branch": "main",
  "show_authors": true
}
```

### Executive defaults

```json
{
  "app_name": "Loudly",
  "audience": "executive",
  "format": "pdf",
  "language": "en",
  "title": "Monthly Release Overview"
}
```

### Multi-repository config

```json
{
  "app_name": "Platform Suite",
  "audience": "changelog",
  "format": "markdown",
  "repos": [
    "/path/to/frontend",
    "/path/to/backend",
    "/path/to/shared-libs"
  ]
}
```

### User-level config

Place at `~/.config/releasepilot/config.json` for cross-project defaults:

```json
{
  "language": "de",
  "audience": "user",
  "show_authors": true
}
```

### Via pyproject.toml

```toml
# pyproject.toml
[tool.releasepilot]
app_name = "MyService"
audience = "technical"
language = "de"
```

### CI/CD-ready config

```json
{
  "$schema": "./schema/releasepilot.schema.json",
  "app_name": "MyApp",
  "audience": "user",
  "language": "en",
  "show_authors": true,
  "output_dir": "release-notes",
  "overwrite": true,
  "export_formats": ["markdown", "pdf"],
  "ci": {
    "enabled": true,
    "artifact_name": "release-notes",
    "fail_on_empty": false,
    "attach_to_release": true
  }
}
```

For full CI/CD integration documentation, see [CI/CD Integration Guide](ci-cd.md).

---

## Invalid Config Examples

### Unknown key

```json
{
  "app_name": "MyApp",
  "theme": "dark"
}
```

**Warning:** `Config: 'theme' — Unknown config key. Valid keys: app_name, audience, branch, ci, export_formats, format, language, output_dir, overwrite, repos, show_authors, show_hashes, title, version`

### Invalid audience value

```json
{
  "audience": "managers"
}
```

**Warning:** `Config: 'audience' — Invalid value 'managers'. Must be one of: changelog, executive, summary, technical, user`

The invalid value is **ignored** (treated as empty) and the built-in default is used instead.

### Wrong type

```json
{
  "repos": "/single/path"
}
```

**Warning:** `Config: 'repos' — Expected a list, got str.`

---

## Validation Behaviour

- **Unknown keys** produce a warning but do not prevent loading.
- **Invalid enum values** (audience, format, language) produce a warning and are ignored (empty string).
- **Wrong types** produce a warning; the field falls back to its default.
- **Missing config file** is silently ignored — no error.
- **Empty config file** is treated as no config.
- **TOML parse errors** are silently ignored — the tool falls back to CLI/defaults.

Warnings are printed to stderr when the CLI loads the config.

---

## What Cannot Be Configured via File

The following must be provided via CLI arguments or guided prompts:

| Setting       | Why                                                   |
|---------------|-------------------------------------------------------|
| `--from`      | Start ref varies per release — rarely a static default|
| `--to`        | End ref is typically `HEAD`                           |
| `--since`     | Date range is usually chosen per run                  |
| `--source-file`| Structured input file path varies                    |
| `--output`    | Output file path varies per run                       |
| `--dry-run`   | Runtime flag, not a persistent default                |

---

## Resetting / Disabling

- **Project config:** Delete or rename the `.releasepilot.json` (or `.releasepilot.toml`) file.
- **User-level config:** Delete `~/.config/releasepilot/config.json`.
- **Smart defaults (preferences):** Delete `~/.config/releasepilot/preferences.json` or set `RELEASEPILOT_NO_PREFS=1`.
