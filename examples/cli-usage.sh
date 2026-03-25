# ──────────────────────────────────────────────────────────────────────────────
# ReleasePilot — CLI Usage Examples
# ──────────────────────────────────────────────────────────────────────────────
#
# This file contains runnable shell examples for common ReleasePilot CLI
# workflows. Each section is self-contained. Copy the commands you need.
#
# Prerequisites:
#   pip install releasepilot          # core
#   pip install "releasepilot[all]"   # with PDF/DOCX export
#
# ──────────────────────────────────────────────────────────────────────────────

# ─── 1. Local Repository — Tag-based ─────────────────────────────────────────
#
# Generate release notes between two tags in the current repository.

releasepilot generate \
  --from v1.0.0 \
  --to v1.1.0 \
  --format markdown \
  --audience changelog

# ─── 2. Local Repository — Date-based ────────────────────────────────────────
#
# Generate notes for all changes since a specific date.

releasepilot generate \
  --since 2026-01-01 \
  --format markdown \
  --audience user \
  --language en

# ─── 3. Export to Multiple Formats ───────────────────────────────────────────

releasepilot export \
  --since 2026-01-01 \
  --format markdown \
  --audience changelog \
  -o release-notes/CHANGELOG.md

releasepilot export \
  --since 2026-01-01 \
  --format pdf \
  --audience user \
  -o release-notes/RELEASE_NOTES.pdf

# ─── 4. Multi-language Output ────────────────────────────────────────────────

releasepilot export \
  --since 2026-01-01 \
  --format markdown \
  --audience user \
  --language pl \
  -o release-notes/RELEASE_NOTES_PL.md

# ─── 5. From Structured File Input ──────────────────────────────────────────
#
# Use a JSON file instead of git history. Useful for testing or manual input.

releasepilot generate \
  --source-file examples/sample_changes.json \
  --format markdown \
  --audience changelog

# ─── 6. Multi-repository (Local) ────────────────────────────────────────────
#
# Generate combined release notes from multiple local repositories.

releasepilot multi \
  ../frontend \
  ../backend \
  ../shared-libs \
  --since 2026-01-01 \
  --format markdown \
  --audience changelog

# ─── 7. Preview & Inspect ───────────────────────────────────────────────────

# Preview classified changes without generating full notes
releasepilot preview --since 2026-02-01

# Collect raw commits and print summary
releasepilot collect --since 2026-02-01

# Analyze commit classification statistics
releasepilot analyze --since 2026-02-01

# ─── 8. Executive / Narrative Audiences ──────────────────────────────────────

releasepilot export \
  --since 2026-01-01 \
  --audience executive \
  --format pdf \
  -o release-notes/EXECUTIVE_BRIEF.pdf

releasepilot export \
  --since 2026-01-01 \
  --audience narrative \
  --format docx \
  -o release-notes/NARRATIVE.docx

# ─── 9. Dashboard (Web UI) ──────────────────────────────────────────────────
#
# Launch the interactive web dashboard for the current repository.

releasepilot serve --repo .

# With a specific port:
releasepilot serve --repo . --port 9000
