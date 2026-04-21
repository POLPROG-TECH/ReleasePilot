#!/usr/bin/env python3
"""ReleasePilot Playground - Demo Runner.

Runs all major ReleasePilot workflows against the sample repositories
and writes outputs to playground/output/.

Usage:
    # Run all demos
    python3 playground/scripts/run_demo.py

    # Run a specific demo group
    python3 playground/scripts/run_demo.py --only executive
    python3 playground/scripts/run_demo.py --only translation
    python3 playground/scripts/run_demo.py --only formats

Available demo groups:
    standard     Standard changelog generation (all audiences)
    executive    Executive PDF/DOCX/Markdown briefs
    translation  Translated outputs (Polish, German, French)
    formats      All output formats (Markdown, PDF, DOCX, JSON, plaintext)
    multi        Multi-repository generation
    daterange    Date-range and days-back workflows
    config       Config-file-driven generation
    all          Everything (default)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLAYGROUND = ROOT / "playground"
REPOS = PLAYGROUND / "repos"
OUTPUT = PLAYGROUND / "output"
CONFIGS = PLAYGROUND / "configs"


class DemoRunner:
    """Orchestrates demo workflows and tracks results."""

    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.skipped: list[str] = []
        self._start = time.monotonic()

    def run(self, name: str, args: list[str], output_file: str = "") -> bool:
        """Run a single ReleasePilot command."""
        cmd = ["releasepilot"] + args
        display = f"  {'▸':} {name:50s}"
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(ROOT),
            )
            if result.returncode == 0:
                # Save stdout if there's output and an output_file
                if output_file and result.stdout.strip():
                    out_path = OUTPUT / output_file
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(result.stdout)
                print(f"{display} ✅")
                self.passed.append(name)
                return True
            else:
                err = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown error"
                print(f"{display} ❌  {err[:80]}")
                self.failed.append((name, err[:200]))
                return False
        except subprocess.TimeoutExpired:
            print(f"{display} ⏱  timeout")
            self.failed.append((name, "timeout"))
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"{display} ❌  {exc}")
            self.failed.append((name, str(exc)[:200]))
            return False

    def run_export(self, name: str, args: list[str], output_file: str) -> bool:
        """Run a ReleasePilot export command."""
        out_path = OUTPUT / output_file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        full_args = args + ["-o", str(out_path)]
        cmd = ["releasepilot"] + full_args
        display = f"  {'▸':} {name:50s}"
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(ROOT),
            )
            if result.returncode == 0 and out_path.exists():
                size = out_path.stat().st_size
                print(f"{display} ✅  ({_human_size(size)})")
                self.passed.append(name)
                return True
            else:
                err = result.stderr.strip().split("\n")[-1] if result.stderr else "no output"
                print(f"{display} ❌  {err[:80]}")
                self.failed.append((name, err[:200]))
                return False
        except subprocess.TimeoutExpired:
            print(f"{display} ⏱  timeout")
            self.failed.append((name, "timeout"))
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"{display} ❌  {exc}")
            self.failed.append((name, str(exc)[:200]))
            return False

    def summary(self) -> int:
        elapsed = time.monotonic() - self._start
        print(f"\n{'─' * 68}")
        print(
            f"  Results: {len(self.passed)} passed, {len(self.failed)} failed, "
            f"{len(self.skipped)} skipped  ({elapsed:.1f}s)"
        )

        if self.failed:
            print("\n  Failed demos:")
            for name, err in self.failed:
                print(f"    ✗ {name}: {err[:100]}")

        print(f"\n  Outputs written to: {OUTPUT}/")
        print(f"{'─' * 68}")
        return 1 if self.failed else 0


# ── Demo groups ──────────────────────────────────────────────────────────────


def demo_standard(r: DemoRunner) -> None:
    """Standard changelog generation - all audiences."""
    print("\n📋 Standard Changelog Generation")
    print("─" * 40)

    repo = str(REPOS / "acme-web")

    # Standard changelog (default audience)
    r.run(
        "acme-web: changelog (default)",
        [
            "generate",
            "--repo",
            repo,
            "--since",
            _days_ago(60),
            "--branch",
            "main",
            "--app-name",
            "Acme Web",
        ],
        "standard/acme-web-changelog.md",
    )

    # Technical audience - show authors + hashes
    r.run(
        "pulse-cli: technical notes",
        [
            "generate",
            "--repo",
            str(REPOS / "pulse-cli"),
            "--since",
            _days_ago(45),
            "--branch",
            "main",
            "--audience",
            "technical",
            "--app-name",
            "Pulse CLI",
            "--show-authors",
            "--show-hashes",
        ],
        "standard/pulse-cli-technical.md",
    )

    # User-facing / What's New
    r.run(
        "acme-web: user-facing / What's New",
        [
            "generate",
            "--repo",
            repo,
            "--since",
            _days_ago(30),
            "--branch",
            "main",
            "--audience",
            "user",
            "--app-name",
            "Acme Web",
        ],
        "standard/acme-web-user.md",
    )

    # Concise summary
    r.run(
        "nova-api: concise summary",
        [
            "generate",
            "--repo",
            str(REPOS / "nova-api"),
            "--since",
            _days_ago(60),
            "--branch",
            "main",
            "--audience",
            "summary",
            "--app-name",
            "Nova API",
        ],
        "standard/nova-api-summary.md",
    )

    # Customer-facing (use user audience - customer is guided-flow only)
    r.run(
        "spark-saas: customer-style (user audience)",
        [
            "generate",
            "--repo",
            str(REPOS / "spark-saas"),
            "--since",
            _days_ago(60),
            "--branch",
            "main",
            "--audience",
            "user",
            "--app-name",
            "Spark SaaS",
        ],
        "standard/spark-saas-customer.md",
    )

    # Existing changelog repo - commit-based generation
    r.run(
        "orbit-mobile: commit-based changelog",
        [
            "generate",
            "--repo",
            str(REPOS / "orbit-mobile"),
            "--since",
            _days_ago(45),
            "--branch",
            "main",
            "--app-name",
            "Orbit Mobile",
        ],
        "standard/orbit-mobile-changelog.md",
    )

    # JSON source file
    r.run(
        "sample: from JSON source file",
        [
            "generate",
            "--source-file",
            str(ROOT / "examples" / "sample_changes.json"),
            "--app-name",
            "SampleApp",
            "--version",
            "2.0.0",
        ],
        "standard/sample-from-json.md",
    )


def demo_executive(r: DemoRunner) -> None:
    """Executive / management brief generation."""
    print("\n📊 Executive Brief Generation")
    print("─" * 40)

    repo = str(REPOS / "spark-saas")

    # Executive markdown
    r.run(
        "spark-saas: executive brief (markdown)",
        [
            "generate",
            "--repo",
            repo,
            "--since",
            _days_ago(90),
            "--branch",
            "main",
            "--audience",
            "executive",
            "--app-name",
            "Spark SaaS",
            "--version",
            "3.0.0",
        ],
        "executive/spark-saas-brief.md",
    )

    # Executive PDF
    r.run_export(
        "spark-saas: executive brief (PDF)",
        [
            "export",
            "--repo",
            repo,
            "--since",
            _days_ago(90),
            "--branch",
            "main",
            "--audience",
            "executive",
            "--format",
            "pdf",
            "--app-name",
            "Spark SaaS",
            "--version",
            "3.0.0",
        ],
        "executive/spark-saas-brief.pdf",
    )

    # Executive DOCX
    r.run_export(
        "spark-saas: executive brief (DOCX)",
        [
            "export",
            "--repo",
            repo,
            "--since",
            _days_ago(90),
            "--branch",
            "main",
            "--audience",
            "executive",
            "--format",
            "docx",
            "--app-name",
            "Spark SaaS",
            "--version",
            "3.0.0",
        ],
        "executive/spark-saas-brief.docx",
    )

    # Executive JSON
    r.run(
        "spark-saas: executive brief (JSON)",
        [
            "generate",
            "--repo",
            repo,
            "--since",
            _days_ago(90),
            "--branch",
            "main",
            "--audience",
            "executive",
            "--format",
            "json",
            "--app-name",
            "Spark SaaS",
            "--version",
            "3.0.0",
        ],
        "executive/spark-saas-brief.json",
    )


def demo_translation(r: DemoRunner) -> None:
    """Translated output demos."""
    print("\n🌐 Translation Demos")
    print("─" * 40)

    repo = str(REPOS / "spark-saas")

    # Polish executive PDF
    r.run_export(
        "spark-saas: executive PDF (Polish)",
        [
            "export",
            "--repo",
            repo,
            "--since",
            _days_ago(90),
            "--branch",
            "main",
            "--audience",
            "executive",
            "--format",
            "pdf",
            "--language",
            "pl",
            "--app-name",
            "Spark SaaS",
            "--version",
            "3.0.0",
        ],
        "translation/spark-saas-brief-pl.pdf",
    )

    # German user-facing markdown
    r.run(
        "acme-web: user-facing (German)",
        [
            "generate",
            "--repo",
            str(REPOS / "acme-web"),
            "--since",
            _days_ago(30),
            "--branch",
            "main",
            "--audience",
            "user",
            "--language",
            "de",
            "--app-name",
            "Acme Web",
        ],
        "translation/acme-web-user-de.md",
    )

    # French changelog
    r.run(
        "nova-api: changelog (French)",
        [
            "generate",
            "--repo",
            str(REPOS / "nova-api"),
            "--since",
            _days_ago(60),
            "--branch",
            "main",
            "--language",
            "fr",
            "--app-name",
            "Nova API",
        ],
        "translation/nova-api-changelog-fr.md",
    )

    # Polish DOCX executive
    r.run_export(
        "spark-saas: executive DOCX (Polish)",
        [
            "export",
            "--repo",
            repo,
            "--since",
            _days_ago(90),
            "--branch",
            "main",
            "--audience",
            "executive",
            "--format",
            "docx",
            "--language",
            "pl",
            "--app-name",
            "Spark SaaS",
            "--version",
            "3.0.0",
        ],
        "translation/spark-saas-brief-pl.docx",
    )

    # Czech summary
    r.run(
        "nova-api: summary (Czech)",
        [
            "generate",
            "--repo",
            str(REPOS / "nova-api"),
            "--since",
            _days_ago(60),
            "--branch",
            "main",
            "--audience",
            "summary",
            "--language",
            "cs",
            "--app-name",
            "Nova API",
        ],
        "translation/nova-api-summary-cs.md",
    )


def demo_formats(r: DemoRunner) -> None:
    """All output format demos."""
    print("\n📄 Output Format Demos")
    print("─" * 40)

    repo = str(REPOS / "acme-web")
    base = [
        "--repo",
        repo,
        "--since",
        _days_ago(60),
        "--branch",
        "main",
        "--app-name",
        "Acme Web",
        "--version",
        "3.0.0",
    ]

    # Markdown (default)
    r.run("acme-web: markdown", ["generate"] + base, "formats/acme-web.md")

    # Plaintext
    r.run(
        "acme-web: plaintext",
        ["generate"] + base + ["--format", "plaintext"],
        "formats/acme-web.txt",
    )

    # JSON
    r.run("acme-web: JSON", ["generate"] + base + ["--format", "json"], "formats/acme-web.json")

    # PDF
    r.run_export("acme-web: PDF", ["export"] + base + ["--format", "pdf"], "formats/acme-web.pdf")

    # DOCX
    r.run_export(
        "acme-web: DOCX", ["export"] + base + ["--format", "docx"], "formats/acme-web.docx"
    )


def demo_multi(r: DemoRunner) -> None:
    """Multi-repository generation."""
    print("\n🔗 Multi-Repository Demo")
    print("─" * 40)

    repo_a = str(REPOS / "atlas-multi-a")
    repo_b = str(REPOS / "atlas-multi-b")

    r.run(
        "atlas: multi-repo combined changelog",
        ["multi", repo_a, repo_b, "--since", _days_ago(30), "--branch", "main"],
        "multi/atlas-combined.md",
    )


def demo_daterange(r: DemoRunner) -> None:
    """Date-range and days-back workflows."""
    print("\n📅 Date-Range Demos")
    print("─" * 40)

    repo = str(REPOS / "acme-web")

    # Last 7 days
    r.run(
        "acme-web: last 7 days",
        [
            "generate",
            "--repo",
            repo,
            "--since",
            _days_ago(7),
            "--branch",
            "main",
            "--app-name",
            "Acme Web",
        ],
        "daterange/acme-web-7d.md",
    )

    # Last 30 days
    r.run(
        "acme-web: last 30 days",
        [
            "generate",
            "--repo",
            repo,
            "--since",
            _days_ago(30),
            "--branch",
            "main",
            "--app-name",
            "Acme Web",
        ],
        "daterange/acme-web-30d.md",
    )

    # Last 90 days (full history)
    r.run(
        "acme-web: last 90 days",
        [
            "generate",
            "--repo",
            repo,
            "--since",
            _days_ago(90),
            "--branch",
            "main",
            "--app-name",
            "Acme Web",
        ],
        "daterange/acme-web-90d.md",
    )

    # Tag-based range
    r.run(
        "acme-web: tag range v2.9.0..v2.10.0",
        [
            "generate",
            "--repo",
            repo,
            "--from",
            "v2.9.0",
            "--to",
            "v2.10.0",
            "--app-name",
            "Acme Web",
            "--version",
            "2.10.0",
        ],
        "daterange/acme-web-tag-range.md",
    )


def demo_config(r: DemoRunner) -> None:
    """Config-inspired generation (parameters matching config file settings)."""
    print("\n⚙️  Config-File-Driven Demos")
    print("─" * 40)

    # Executive English (matches executive-english.json settings)
    r.run(
        "config: executive-english.json",
        [
            "generate",
            "--repo",
            str(REPOS / "spark-saas"),
            "--since",
            _days_ago(90),
            "--branch",
            "main",
            "--audience",
            "executive",
            "--app-name",
            "Spark SaaS",
        ],
        "config/executive-english.md",
    )

    # Technical detailed (matches technical-detailed.json settings)
    r.run(
        "config: technical-detailed.json",
        [
            "generate",
            "--repo",
            str(REPOS / "pulse-cli"),
            "--since",
            _days_ago(45),
            "--branch",
            "main",
            "--audience",
            "technical",
            "--app-name",
            "Pulse CLI",
            "--show-authors",
            "--show-hashes",
        ],
        "config/technical-detailed.md",
    )

    # Customer-facing (uses user audience - closest match)
    r.run(
        "config: customer-facing.json",
        [
            "generate",
            "--repo",
            str(REPOS / "spark-saas"),
            "--since",
            _days_ago(60),
            "--branch",
            "main",
            "--audience",
            "user",
            "--app-name",
            "Spark SaaS",
        ],
        "config/customer-facing.md",
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _days_ago(n: int) -> str:
    """Return ISO date for N days ago."""
    from datetime import date, timedelta

    return (date.today() - timedelta(days=n)).isoformat()


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


# ── Demo group registry ─────────────────────────────────────────────────────

GROUPS = {
    "standard": demo_standard,
    "executive": demo_executive,
    "translation": demo_translation,
    "formats": demo_formats,
    "multi": demo_multi,
    "daterange": demo_daterange,
    "config": demo_config,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="ReleasePilot Playground Demo Runner")
    parser.add_argument(
        "--only",
        choices=list(GROUPS) + ["all"],
        default="all",
        help="Run only a specific demo group",
    )
    parser.add_argument("--setup", action="store_true", help="Run repo setup before demos")
    args = parser.parse_args()

    # Check repos exist
    if args.setup or not REPOS.exists() or not list(REPOS.iterdir()):
        print("Setting up sample repositories first...\n")
        subprocess.run([sys.executable, str(PLAYGROUND / "scripts" / "setup_repos.py")], check=True)
        print()

    # Prepare output directory
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    print("🎯 ReleasePilot Playground - Demo Runner")
    print("=" * 68)

    runner = DemoRunner()

    if args.only == "all":
        for fn in GROUPS.values():
            fn(runner)
    else:
        GROUPS[args.only](runner)

    sys.exit(runner.summary())


if __name__ == "__main__":
    main()
