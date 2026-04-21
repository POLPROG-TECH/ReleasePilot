#!/usr/bin/env python3
"""Bootstrap sample git repositories for the ReleasePilot playground.

Creates several small but realistic repositories with different commit
histories, tags, and structures to exercise all major ReleasePilot flows.

Usage:
    python3 playground/scripts/setup_repos.py

Repos created in playground/repos/:
    acme-web/       - Web app with tags and mixed commit types
    nova-api/       - API service with conventional commits, no tags
    orbit-mobile/   - Mobile app with existing CHANGELOG.md
    pulse-cli/      - CLI tool with security/breaking changes
    spark-saas/     - SaaS platform for executive/customer demos
    atlas-multi-a/  - Microservice A (for multi-repo demo)
    atlas-multi-b/  - Microservice B (for multi-repo demo)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

REPOS_DIR = Path(__file__).resolve().parent.parent / "repos"

# ── Commit specifications ────────────────────────────────────────────────────
# Each tuple: (days_ago, message, files_dict)

ACME_WEB_COMMITS = [
    (85, "feat(auth): add OAuth2 login with Google provider", {"src/auth.py": "# OAuth2\n"}),
    (80, "fix(auth): resolve token refresh race condition", {"src/auth.py": "# OAuth2 fixed\n"}),
    (
        75,
        "feat(dashboard): implement real-time analytics widget",
        {"src/dashboard.py": "# Analytics\n"},
    ),
    (70, "docs: update API authentication guide", {"docs/auth.md": "# Auth guide\n"}),
    (65, "perf(db): optimize user query with composite index", {"src/db.py": "# Indexed\n"}),
    (60, "fix(ui): correct dark mode color contrast issues", {"src/ui.css": "/* dark mode */\n"}),
    (55, "feat(search): add full-text search with Elasticsearch", {"src/search.py": "# FTS\n"}),
    (50, "refactor(api): migrate from REST to GraphQL endpoints", {"src/api.py": "# GraphQL\n"}),
    (45, "fix(payments): handle expired card retry logic", {"src/payments.py": "# Retry\n"}),
    (40, "feat(notifications): add push notification support", {"src/notif.py": "# Push\n"}),
    (35, "chore(deps): upgrade React from 18 to 19", {"package.json": '{"react":"19"}\n'}),
    (
        30,
        "security: patch XSS vulnerability in comment rendering",
        {"src/comments.py": "# Patched\n"},
    ),
    (25, "feat(export): add PDF export for reports", {"src/export.py": "# PDF\n"}),
    (20, "improvement(ux): streamline onboarding wizard flow", {"src/onboard.py": "# Wizard\n"}),
    (15, "fix(i18n): correct Polish date formatting", {"src/i18n.py": "# PL dates\n"}),
    (10, "feat(api): add rate limiting middleware", {"src/ratelimit.py": "# Rate limit\n"}),
    (7, "perf(cache): implement Redis caching layer", {"src/cache.py": "# Redis\n"}),
    (5, "fix(upload): handle large file uploads gracefully", {"src/upload.py": "# Large files\n"}),
    (3, "feat(teams): add team management and role-based access", {"src/teams.py": "# RBAC\n"}),
    (1, "docs: add deployment runbook for v3.0", {"docs/deploy.md": "# Runbook\n"}),
]

ACME_WEB_TAGS = [
    (80, "v2.9.0"),  # matches commit at day 80
    (50, "v2.10.0"),  # matches commit at day 50
    (10, "v3.0.0-rc.1"),  # matches commit at day 10
]

NOVA_API_COMMITS = [
    (60, "feat: implement user registration endpoint", {"src/users.go": "// Registration\n"}),
    (55, "feat: add JWT authentication middleware", {"src/auth.go": "// JWT\n"}),
    (50, "fix: resolve database connection pool exhaustion", {"src/db.go": "// Pool fix\n"}),
    (45, "feat: create product catalog CRUD operations", {"src/products.go": "// CRUD\n"}),
    (40, "perf: add database query result caching", {"src/cache.go": "// Cache\n"}),
    (35, "fix: correct pagination offset calculation", {"src/pagination.go": "// Offset\n"}),
    (30, "feat: implement webhook notification system", {"src/webhooks.go": "// Hooks\n"}),
    (25, "improvement: add request validation middleware", {"src/validate.go": "// Validate\n"}),
    (20, "feat: add API versioning support (v1/v2)", {"src/router.go": "// Versioning\n"}),
    (15, "fix: handle concurrent write conflicts in orders", {"src/orders.go": "// Conflict\n"}),
    (10, "security: sanitize SQL inputs in search endpoint", {"src/search.go": "// Sanitize\n"}),
    (5, "feat: add health check and readiness endpoints", {"src/health.go": "// Health\n"}),
    (2, "improvement: add structured JSON logging", {"src/logger.go": "// Structured\n"}),
]

ORBIT_MOBILE_CHANGELOG = """\
# Changelog

## [2.5.0] - 2026-02-15

### Added
- Offline mode with local data sync
- Biometric authentication (Face ID / fingerprint)

### Fixed
- App crash on low memory devices
- Push notification badge count mismatch

## [2.4.0] - 2026-01-10

### Added
- Dark mode support
- Share to social media feature

### Changed
- Redesigned settings screen layout

### Fixed
- Memory leak in image gallery view
"""

ORBIT_MOBILE_COMMITS = [
    (45, "feat(camera): add QR code scanner", {"src/camera.swift": "// QR\n"}),
    (40, "fix(sync): resolve offline sync conflict", {"src/sync.swift": "// Conflict\n"}),
    (35, "feat(map): integrate MapKit with custom markers", {"src/map.swift": "// Maps\n"}),
    (30, "improvement(ui): add haptic feedback to buttons", {"src/haptic.swift": "// Haptic\n"}),
    (25, "fix(memory): reduce image cache memory footprint", {"src/image.swift": "// Memory\n"}),
    (20, "feat(share): add clipboard sharing support", {"src/share.swift": "// Clipboard\n"}),
    (15, "perf(startup): reduce cold start time by 40%", {"src/startup.swift": "// Startup\n"}),
    (10, "fix(notifications): correct deep link routing", {"src/deeplink.swift": "// Deep link\n"}),
    (
        5,
        "feat(accessibility): add VoiceOver support for all views",
        {"src/a11y.swift": "// A11y\n"},
    ),
    (2, "docs: update App Store release notes template", {"docs/appstore.md": "# Template\n"}),
]

PULSE_CLI_COMMITS = [
    (50, "feat: add init command for project scaffolding", {"src/init.rs": "// Init\n"}),
    (45, "feat: implement config file parsing (TOML/YAML)", {"src/config.rs": "// Config\n"}),
    (
        40,
        "feat!: change default output format from JSON to YAML",
        {"src/output.rs": "// YAML default\n"},
    ),
    (35, "security: fix path traversal in file import command", {"src/import.rs": "// Patched\n"}),
    (30, "feat: add watch mode with file system notifications", {"src/watch.rs": "// Watch\n"}),
    (25, "fix: resolve panic on empty input file", {"src/parse.rs": "// Empty check\n"}),
    (20, "feat!: remove deprecated --legacy flag", {"src/cli.rs": "// No legacy\n"}),
    (15, "security: validate TLS certificates in HTTP client", {"src/http.rs": "// TLS\n"}),
    (
        10,
        "improvement: add colored terminal output with auto-detect",
        {"src/color.rs": "// Color\n"},
    ),
    (7, "fix: correct exit code for partial failures", {"src/exit.rs": "// Exit code\n"}),
    (
        5,
        "feat: add shell completion generation (bash/zsh/fish)",
        {"src/complete.rs": "// Completion\n"},
    ),
    (3, "perf: parallelize file processing with rayon", {"src/parallel.rs": "// Rayon\n"}),
    (1, "security: upgrade dependency to fix CVE-2026-1234", {"Cargo.toml": "# Upgraded\n"}),
]

SPARK_SAAS_COMMITS = [
    (88, "feat(billing): implement usage-based billing engine", {"src/billing.ts": "// Billing\n"}),
    (82, "feat(onboarding): add guided product tour", {"src/tour.ts": "// Tour\n"}),
    (
        76,
        "fix(billing): correct proration calculation for upgrades",
        {"src/prorate.ts": "// Prorate\n"},
    ),
    (70, "feat(analytics): add real-time usage dashboard", {"src/analytics.ts": "// Usage\n"}),
    (64, "security: implement SOC 2 audit logging", {"src/audit.ts": "// SOC2\n"}),
    (
        58,
        "feat(api): add GraphQL subscription for live updates",
        {"src/subscriptions.ts": "// Live\n"},
    ),
    (52, "improvement(perf): optimize database connection pooling", {"src/pool.ts": "// Pool\n"}),
    (
        46,
        "feat(export): add data export in CSV and Excel formats",
        {"src/export.ts": "// Export\n"},
    ),
    (40, "fix(auth): resolve SSO session timeout handling", {"src/sso.ts": "// SSO\n"}),
    (
        34,
        "feat(integrations): add Slack and Teams notifications",
        {"src/integrations.ts": "// Slack\n"},
    ),
    (28, "feat(rbac): implement granular permission system", {"src/permissions.ts": "// RBAC\n"}),
    (22, "perf(search): implement Elasticsearch full-text search", {"src/search.ts": "// ES\n"}),
    (
        16,
        "fix(webhook): add retry logic with exponential backoff",
        {"src/webhook.ts": "// Retry\n"},
    ),
    (10, "feat(multi-tenant): add workspace isolation", {"src/tenant.ts": "// Multi-tenant\n"}),
    (7, "security: add IP allowlist for API access", {"src/firewall.ts": "// IP allow\n"}),
    (4, "feat(reports): add scheduled report generation", {"src/reports.ts": "// Reports\n"}),
    (2, "improvement(ux): redesign main navigation sidebar", {"src/nav.ts": "// Nav\n"}),
    (1, "fix(notifications): correct email template rendering", {"src/email.ts": "// Email\n"}),
]

ATLAS_A_COMMITS = [
    (30, "feat: add user profile service endpoint", {"src/profile.py": "# Profile\n"}),
    (25, "fix: correct database migration script ordering", {"src/migrate.py": "# Migration\n"}),
    (20, "feat: implement session management with Redis", {"src/session.py": "# Session\n"}),
    (15, "improvement: add health check endpoint", {"src/health.py": "# Health\n"}),
    (10, "fix: resolve race condition in cache invalidation", {"src/cache.py": "# Cache fix\n"}),
    (5, "perf: optimize user lookup with bloom filter", {"src/bloom.py": "# Bloom\n"}),
]

ATLAS_B_COMMITS = [
    (28, "feat: implement order processing pipeline", {"src/orders.js": "// Orders\n"}),
    (22, "fix: correct inventory count after cancellation", {"src/inventory.js": "// Inventory\n"}),
    (18, "feat: add payment gateway integration (Stripe)", {"src/payments.js": "// Stripe\n"}),
    (12, "security: sanitize user input in order notes", {"src/sanitize.js": "// Sanitize\n"}),
    (
        8,
        "improvement: add order tracking webhook notifications",
        {"src/tracking.js": "// Tracking\n"},
    ),
    (3, "fix: handle timezone conversion in delivery estimates", {"src/timezone.js": "// TZ\n"}),
]


def _run(cmd: list[str], cwd: str, env: dict | None = None) -> None:
    """Run a command silently."""
    merged = {**os.environ, **(env or {})}
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, env=merged)


def _create_repo(
    name: str,
    commits: list[tuple],
    *,
    tags: list[tuple] | None = None,
    changelog: str | None = None,
) -> Path:
    """Create a sample git repo with realistic commit history."""
    repo = REPOS_DIR / name
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)

    env = {
        "GIT_AUTHOR_NAME": "Demo User",
        "GIT_AUTHOR_EMAIL": "demo@example.com",
        "GIT_COMMITTER_NAME": "Demo User",
        "GIT_COMMITTER_EMAIL": "demo@example.com",
    }

    _run(["git", "init", "-b", "main"], str(repo), env)
    _run(["git", "config", "user.email", "demo@example.com"], str(repo))
    _run(["git", "config", "user.name", "Demo User"], str(repo))

    # Write changelog if provided (before other commits)
    if changelog:
        cl_path = repo / "CHANGELOG.md"
        cl_path.write_text(changelog)
        _run(["git", "add", "."], str(repo))
        date_str = _date_str(90)
        _commit(repo, "docs: add changelog", date_str, env)

    # Create commits
    tag_map = {}
    if tags:
        for days_ago, tag in tags:
            tag_map[days_ago] = tag

    for days_ago, message, files in commits:
        for relpath, content in files.items():
            fpath = repo / relpath
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
        _run(["git", "add", "."], str(repo))
        date_str = _date_str(days_ago)
        _commit(repo, message, date_str, env)

        if days_ago in tag_map:
            _run(
                ["git", "tag", "-a", tag_map[days_ago], "-m", f"Release {tag_map[days_ago]}"],
                str(repo),
                env,
            )

    return repo


def _commit(repo: Path, message: str, date_str: str, env: dict) -> None:
    merged = {**os.environ, **env, "GIT_AUTHOR_DATE": date_str, "GIT_COMMITTER_DATE": date_str}
    subprocess.run(
        ["git", "commit", "-m", message], cwd=str(repo), check=True, capture_output=True, env=merged
    )


def _date_str(days_ago: int) -> str:
    dt = datetime.now() - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def main() -> None:
    print("🚀 ReleasePilot Playground - Setting up sample repositories\n")

    if REPOS_DIR.exists():
        print("   Cleaning existing repos...")
        shutil.rmtree(REPOS_DIR)
    REPOS_DIR.mkdir(parents=True)

    repos = [
        (
            "acme-web",
            ACME_WEB_COMMITS,
            ACME_WEB_TAGS,
            None,
            "Web app - tags, mixed commit types, 85-day history",
        ),
        (
            "nova-api",
            NOVA_API_COMMITS,
            None,
            None,
            "API service - conventional commits, no tags, 60-day history",
        ),
        (
            "orbit-mobile",
            ORBIT_MOBILE_COMMITS,
            None,
            ORBIT_MOBILE_CHANGELOG,
            "Mobile app - existing CHANGELOG.md",
        ),
        ("pulse-cli", PULSE_CLI_COMMITS, None, None, "CLI tool - security fixes, breaking changes"),
        (
            "spark-saas",
            SPARK_SAAS_COMMITS,
            None,
            None,
            "SaaS platform - executive/customer demo, 88-day history",
        ),
        (
            "atlas-multi-a",
            ATLAS_A_COMMITS,
            None,
            None,
            "Microservice A - user service (multi-repo demo)",
        ),
        (
            "atlas-multi-b",
            ATLAS_B_COMMITS,
            None,
            None,
            "Microservice B - order service (multi-repo demo)",
        ),
    ]

    for name, commits, tags, changelog, desc in repos:
        print(f"   📦 {name:20s} - {desc}")
        _create_repo(name, commits, tags=tags, changelog=changelog)

    print(f"\n✅ Created {len(repos)} sample repositories in {REPOS_DIR}/")
    print("\nRun the demo with:")
    print("    python3 playground/scripts/run_demo.py")


if __name__ == "__main__":
    main()
