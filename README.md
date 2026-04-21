<div align="center">
  <img alt="ReleasePilot" src="assets/logo-full.svg" width="520">
</div>

<p align="center">
  <a href="https://github.com/POLPROG-TECH/ReleasePilot/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/POLPROG-TECH/ReleasePilot/ci.yml?branch=main&style=flat-square&label=CI&logo=github" alt="CI"></a>
  <img src="https://img.shields.io/badge/tests-922%20passed-22c55e?style=flat-square&logo=pytest&logoColor=white" alt="Tests: 922 passed">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-6366f1?style=flat-square" alt="License: AGPL-3.0"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
</p>

<p align="center">
  <b>Generate polished, audience-aware release notes from any git repository.</b><br>
  <sub>Interactive web dashboard · SSE real-time progress · Executive briefs · Customer-facing notes · Technical changelogs · PDF &amp; DOCX export</sub>
</p>

<p align="center">
  <a href="#what-is-releasepilot">About</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#screenshots">Screenshots</a> ·
  <a href="#web-server-mode">Web Server</a> ·
  <a href="#cli-mode">CLI Mode</a> ·
  <a href="#features">Features</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#opsportal-integration">OpsPortal</a>
</p>

<p align="center">
  <a href="https://buymeacoffee.com/polprog"><img src="https://img.shields.io/badge/Support%20this%20project-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Support this project"></a>
</p>

---

## What is ReleasePilot?

ReleasePilot turns source changes - git commits, tags, pull requests - into polished release notes tailored for different audiences. It is **not** a raw changelog dump. It classifies, filters, deduplicates, and groups changes to produce release communication that reads naturally.

The **primary mode** is an interactive web dashboard powered by FastAPI and Jinja2 SSR, with real-time generation progress via Server-Sent Events. A full CLI is also available for scripting and CI/CD pipelines.

---

## Screenshots

### Interactive Guide

The Guide tab explains how ReleasePilot works - the pipeline stages, all 8 audience modes, output formats, best practices, and CLI reference.

<p align="center">
  <img src="docs/assets/screenshots/guide-overview.png" alt="ReleasePilot - interactive guide with pipeline, audiences, and formats" width="800">
</p>

### Source Configuration Wizard

The wizard guides you through a multi-step flow: source selection (local or remote), repository configuration (single or multi-repo), release scope, audience, and format - with built-in validation at every step. Supports GitHub and GitLab repositories via URL. Access tokens are context-aware: optional for public GitHub repositories, required for private repos and GitLab. See [Web Wizard Documentation](docs/web-wizard.md) for full details.

<p align="center">
  <img src="docs/assets/screenshots/wizard-source-config.png" alt="ReleasePilot - source configuration wizard with date range presets" width="800">
</p>

### Generation Complete

After the pipeline processes your commits, you see a summary of changes and output size before previewing and exporting.

<p align="center">
  <img src="docs/assets/screenshots/wizard-generation-complete.png" alt="ReleasePilot - generation complete with change stats" width="800">
</p>

---

## Table of Contents

- [What is ReleasePilot?](#what-is-releasepilot)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)
- [Web Server Mode](#web-server-mode)
- [Web Wizard](docs/web-wizard.md)
- [CLI Mode](#cli-mode)
- [Features](#features)
- [Configuration](#configuration)
- [Installation](#installation)
- [Architecture](#architecture)
- [OpsPortal Integration](#opsportal-integration)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)

---

## Quick Start

### Web Server (recommended)

```bash
# Start the interactive dashboard
releasepilot serve

# Specify a repository and port
releasepilot serve --repo /path/to/repo --port 8082

# Enable debug logging
releasepilot serve --repo . --verbose
```

Open **http://127.0.0.1:8082** in your browser to access the interactive dashboard.

### CLI

```bash
# Generate release notes for the current repository
releasepilot generate

# Interactive guided workflow
releasepilot guide

# Generate and export as PDF
releasepilot generate --format pdf --output notes.pdf
```

---

## Web Server Mode

The web server is the **primary operating model** for ReleasePilot. It provides a self-contained interactive dashboard served via FastAPI with Jinja2 server-side rendering.

### Startup

```bash
releasepilot serve [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--repo`, `-r` | `.` | Path to the git repository to analyze |
| `--host` | `127.0.0.1` | Host address to bind |
| `--port`, `-p` | `8082` | Port number |
| `--verbose`, `-v` | off | Enable debug logging |

**App factory** (for programmatic usage or ASGI deployment):

```python
from releasepilot.web.server import create_app

app = create_app(config, root_path="")
```

### API Endpoints

ReleasePilot exposes 12 HTTP routes covering health monitoring, generation control, dashboard rendering, and configuration.

**Health & Status**
- `GET /health/live` - liveness probe
- `GET /health/ready` - readiness probe
- `GET /api/status` - version, uptime, and generation progress

**Generation** - trigger async release-notes generation, stream real-time progress via SSE, and retrieve results.

**Dashboard** - interactive HTML dashboard at `/`, raw HTML export via `/api/dashboard/html`.

**Configuration** - view and update generation settings at runtime via `GET/PUT /api/config`.

### Server-Sent Events

The `/api/generate/stream` endpoint delivers real-time progress updates during release-notes generation. Connect with any SSE-compatible client (browser `EventSource`, `curl -N`, etc.) to receive incremental status messages as commits are collected, classified, deduplicated, and rendered.

### Iframe Embedding

By default, ReleasePilot sets headers that prevent iframe embedding. To allow framing (e.g., when embedding inside OpsPortal), set the environment variable:

```bash
export RELEASEPILOT_ALLOW_FRAMING=true
releasepilot serve --port 8082
```

---

## CLI Mode

The CLI provides commands for scripting, CI/CD pipelines, and terminal-based workflows.

```bash
releasepilot <command> [OPTIONS]
```

| Command | Description |
|---------|-------------|
| `serve` | **Start the web server** (primary mode) |
| `generate` | Generate release notes |
| `preview` | Preview release notes in the terminal |
| `collect` | Collect raw commits from a range |
| `analyze` | Analyze and classify commit types |
| `export` | Export release notes to a file |
| `multi` | Multi-repository generation |
| `dashboard` | Generate a static HTML dashboard |
| `guide` | Interactive guided workflow |

### CLI Examples

```bash
# Generate notes between two tags
releasepilot generate --from v1.0.0 --to v1.1.0

# Preview in terminal with user-facing audience
releasepilot preview --audience user

# Export as DOCX
releasepilot export --format docx --output release-notes.docx

# Collect raw commits as JSON
releasepilot collect --from v1.0.0 --to HEAD

# Multi-repo generation
releasepilot multi --repos repo1/ repo2/ --output combined-notes.md

# Generate a static HTML dashboard
releasepilot dashboard --output dashboard.html
```

---

## Features

### Audience Modes

ReleasePilot supports **8 audience modes** that control tone, detail level, and structure:

| Mode | Description |
|------|-------------|
| `TECHNICAL` | Full technical detail for developers |
| `USER` | User-facing notes for end users |
| `SUMMARY` | Concise summary of changes |
| `CHANGELOG` | Traditional changelog format |
| `CUSTOMER` | Customer-facing release communication |
| `EXECUTIVE` | Board/management-ready executive brief |
| `NARRATIVE` | Story-driven technical narrative |
| `CUSTOMER_NARRATIVE` | Story-driven customer-facing narrative |

### Output Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| Markdown | `.md` | Default format |
| Plaintext | `.txt` | Plain text output |
| JSON | `.json` | Structured data for integrations |
| PDF | `.pdf` | Requires `[export]` extras |
| DOCX | `.docx` | Requires `[export]` extras |

### Commit Classification

- **Conventional Commits** parsing (`feat:`, `fix:`, `chore:`, etc.)
- **Keyword-based fallback** classification for non-conventional commits
- Categories: features, fixes, refactoring, documentation, tests, chores, and more

### Smart Deduplication

ReleasePilot removes redundant entries using multiple strategies:

- **Exact hash** matching
- **PR merge** detection and grouping
- **Token overlap** - 80% similarity threshold for near-duplicate detection

### Additional Capabilities

- **Noise filtering** - merge commits, WIP, fixups, and trivial changes are filtered out
- **10 languages** - all structural labels are translated
- **Pipeline transparency** - shows collected → filtered → deduplicated counts
- **Deterministic output** - same input always produces the same result
- **Multi-repository** support
- **Structured input** - JSON files for CI pipelines or manual supplementation
- **Branch validation** - invalid branches rejected with suggestions
- **Overwrite protection** - warns before overwriting existing files

---

## Configuration

ReleasePilot searches for configuration files in the following order:

| Priority | File |
|----------|------|
| 1 | `.releasepilot.json` |
| 2 | `releasepilot.json` |
| 3 | `.releasepilot.toml` |
| 4 | `releasepilot.toml` |
| 5 | `pyproject.toml` → `[tool.releasepilot]` |
| 6 | `~/.config/releasepilot/config.json` |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `RELEASEPILOT_NO_PREFS` | Set to `1` to disable config file loading |
| `RELEASEPILOT_ALLOW_FRAMING` | Set to `true` to allow iframe embedding |

### Example Configuration

```json
{
  "audience": "user",
  "format": "markdown",
  "language": "en",
  "noise_filter": true,
  "deduplication": true
}
```

---

## Installation

**Requirements:** Python 3.12+

```bash
# Core installation
pip install -e .

# With PDF/DOCX export support
pip install -e ".[export]"

# With development/test dependencies
pip install -e ".[dev]"

# All extras
pip install -e ".[all]"
```

Verify the installation:

```bash
releasepilot --version
```

> **Note:** ReleasePilot works with **any** git repository - Python, JavaScript, Rust, Go, or any other language. The target repository does not need to be a Python project.

> **Corporate network (Zscaler / VPN)?** If `pip install` fails with SSL errors, see [Corporate Network setup](#corporate-network-zscaler--vpn--proxy) below.

### Corporate Network (Zscaler / VPN / Proxy)

If you're behind a corporate proxy that intercepts HTTPS (e.g. Zscaler, Netskope), you need to export the corporate CA bundle **before** installing dependencies or connecting to GitLab.

<details>
<summary><b>macOS / Linux</b></summary>

```bash
# 1. Export corporate CA certificates (macOS)
security find-certificate -a -p \
  /Library/Keychains/System.keychain \
  /System/Library/Keychains/SystemRootCertificates.keychain \
  > ~/combined-ca-bundle.pem

# On Linux, the CA bundle is usually already available:
#   /etc/ssl/certs/ca-certificates.crt          (Debian/Ubuntu)
#   /etc/pki/tls/certs/ca-bundle.crt            (RHEL/Fedora)
# If your proxy adds its own CA, ask your IT department for the .pem file
# and append it: cat corporate-ca.pem >> ~/combined-ca-bundle.pem

# 2. Configure SSL trust (add to ~/.zshrc or ~/.bashrc to persist)
export SSL_CERT_FILE=~/combined-ca-bundle.pem
export REQUESTS_CA_BUNDLE=~/combined-ca-bundle.pem

# 3. (Optional) Also configure git to use the same CA bundle
git config --global http.sslCAInfo ~/combined-ca-bundle.pem

# 4. Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 5. Set token for private repos
export RELEASEPILOT_GITLAB_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx"

# 6. Start
releasepilot serve
```
</details>

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
# 1. Export corporate CA certificate
# Ask your IT department for the corporate CA .pem file, or export it from
# certmgr.msc → Trusted Root Certification Authorities → Certificates
# Right-click → All Tasks → Export → Base-64 encoded X.509 (.CER)
# Save as: %USERPROFILE%\corporate-ca-bundle.pem

# 2. Configure SSL trust (add to your PowerShell profile to persist)
$env:SSL_CERT_FILE = "$env:USERPROFILE\corporate-ca-bundle.pem"
$env:REQUESTS_CA_BUNDLE = "$env:USERPROFILE\corporate-ca-bundle.pem"

# 3. (Optional) Also configure git to use the same CA bundle
git config --global http.sslCAInfo "$env:USERPROFILE\corporate-ca-bundle.pem"

# 4. Install
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 5. Set token for private repos
$env:RELEASEPILOT_GITLAB_TOKEN = "glpat-xxxxxxxxxxxxxxxxxxxx"

# 6. Start
releasepilot serve
```

> **Tip:** To make environment variables permanent on Windows, use `[System.Environment]::SetEnvironmentVariable("SSL_CERT_FILE", "$env:USERPROFILE\corporate-ca-bundle.pem", "User")` or set them via System Properties → Environment Variables.
</details>

---

## Architecture

```
src/releasepilot/
├── cli/              # Click CLI commands (generate, preview, collect, export, guide, serve)
├── web/              # FastAPI server, Jinja2 templates, SSE streaming
├── pipeline/         # Commit collection, classification, deduplication, rendering
├── domain/           # Models, audience modes, format definitions
├── exporters/        # Markdown, JSON, plain text, PDF, DOCX output
├── i18n/             # 10-language translation support
└── shared/           # Logging, constants, utilities
```

**Key design principles:**

- **Pipeline architecture** - commits flow through collect → filter → classify → deduplicate → render stages
- **Audience-driven output** - audience mode controls tone, detail, and structure throughout the pipeline
- **Format-agnostic rendering** - the same pipeline feeds multiple exporters (MD, JSON, PDF, DOCX)
- **Deterministic output** - same input always produces the same result

See the source code for detailed implementation.

---

## OpsPortal Integration

ReleasePilot integrates with [OpsPortal](../OpsPortal) as a **subprocess web tool**:

- Registered as a `SUBPROCESS_WEB` tool on port **8082**
- OpsPortal auto-starts ReleasePilot via `releasepilot serve --port 8082`
- Health monitored through `/health/live`
- Embedded in the OpsPortal UI via iframe
- `RELEASEPILOT_ALLOW_FRAMING=true` is set automatically by OpsPortal

No manual configuration is needed - OpsPortal manages the lifecycle automatically.

---

## Troubleshooting

For detailed solutions to common issues, see [docs/troubleshooting.md](docs/troubleshooting.md).

| Problem | Quick Fix |
|---------|-----------|
| **SSL certificate errors** during `pip install` or GitLab access | Export corporate CA bundle: `export SSL_CERT_FILE=~/combined-ca-bundle.pem` - see [Corporate Network setup](#corporate-network-zscaler--vpn--proxy) |
| **GitLab repos return 404** | Set `RELEASEPILOT_GITLAB_TOKEN` via env var or config file |
| **Wrong GitLab hostname** | Check with `git remote -v` in a local clone |
| **Transient 502/503/504** | Automatic retry with back-off - no action needed |
| **Port already in use** | `lsof -i :8082 -t \| xargs kill -9` or use `--port 9082` |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
```

---

## Author

Created and maintained by **[POLPROG](https://polprog.pl/)** ([@polprog-tech](https://github.com/polprog-tech)).

- **Report issues:** [GitHub Issues](https://github.com/polprog-tech/ReleasePilot/issues)
- **Feature requests:** [GitHub Discussions](https://github.com/polprog-tech/ReleasePilot/discussions)
- **Documentation:** [docs/architecture.md](docs/architecture.md)

---

## Contributing & Community

- [Contributing Guide](CONTRIBUTING.md) - development setup, code style, PR guidance
- [Code of Conduct](CODE_OF_CONDUCT.md) - expected behavior for contributors and maintainers
- [Security Policy](SECURITY.md) - how to privately report security vulnerabilities
- [Changelog](CHANGELOG.md) - release history and notable changes

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
