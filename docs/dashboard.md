# Dashboard

ReleasePilot generates a self-contained interactive HTML dashboard that visualises your release notes pipeline.

## Usage

```bash
releasepilot dashboard                          # Generate release-dashboard.html
releasepilot dashboard --open                   # Generate and open in browser
releasepilot dashboard -o build/release.html    # Custom output path
releasepilot dashboard --from v1.0.0 --version 1.1.0
```

## Architecture

```
CLI (dashboard command)
  │
  ├── DashboardUseCase.execute(settings)
  │     ├── build_release_range()
  │     ├── collect()
  │     ├── process_with_stats()
  │     ├── compose()
  │     ├── render() → artifact previews
  │     └── returns DashboardData
  │
  ├── HtmlReporter.render(data)
  │     ├── Serializes DashboardData → JSON
  │     ├── Replaces __PLACEHOLDER__ tokens
  │     └── Returns self-contained HTML string
  │
  └── Writes HTML file, optionally opens browser
```

### Key files

| File | Purpose |
|------|---------|
| `dashboard/schema.py` | `DashboardData` and related frozen dataclasses |
| `dashboard/use_case.py` | Orchestrates pipeline and builds dashboard data |
| `dashboard/reporter.py` | Serialises data and renders HTML template |
| `dashboard/templates.py` | Complete HTML/CSS/JS template (~60KB) |

## Data Model

`DashboardData` is a frozen dataclass containing:

- **Source info** — repo path, branch, from/to refs, version, app name
- **Pipeline results** — total changes, change entries, pipeline stage stats, category distribution
- **Highlights & breaking** — extracted high-importance and breaking changes
- **Groups** — changes grouped by category
- **Artifacts** — rendered release notes previews (Markdown, JSON)
- **Metadata** — generation timestamp, language, audience, format
- **Diagnostics** — messages for the empty/first-run state

### Computed properties

- `is_empty` — true when no changes collected
- `total_breaking` — count of breaking changes
- `total_highlights` — count of highlighted changes
- `categories_used` — number of distinct categories
- `total_authors` — number of unique contributors
- `scopes_used` — sorted tuple of component scopes

## Tabs

### Overview

Stat cards showing total changes, categories, contributors, breaking changes, and highlights. Includes a colour-coded distribution bar, release range info, and grouped change cards.

### Changes

Filterable, sortable, paginated table of all collected changes. Filters: search text, category, importance, scope. Columns: title, category badge, scope, importance, authors, date, commit hash.

### Artifacts

Preview tabs for each generated artifact (audience + format). Copy to clipboard and download controls. Shows file size.

### Quality

Pipeline flow visualisation (collected → classified → filtered → deduplicated) with count and removal indicators. Classification breakdown table with percentage bars. Release metadata table.

## Settings

Accessible via the ⚙ Settings button in the header. Persisted in `localStorage`.

| Setting | Options | Key |
|---------|---------|-----|
| Language | English, Polski | `rp-locale` |
| Theme | Light, Dark, Midnight | `rp-theme` |
| Density | Comfortable, Compact | `rp-density` |
| Rows per page | 10, 25, 50, 100 | `rp-rows` |
| Custom colours | Primary, Secondary, Tertiary | `rp-custom-colors` |

## Theming

Three built-in themes using CSS custom properties on `[data-theme]`:

- **Light** — white surfaces, warm orange header
- **Dark** — dark grey surfaces, muted orange header
- **Midnight** — near-black surfaces, deep orange header

Custom accent colours override `--custom-primary`, `--custom-secondary`, `--custom-tertiary`.

## Internationalisation

The dashboard supports English and Polish via the `data-i18n` attribute system. The `_t(key)` function resolves translations with English fallback.

## Accessibility

- Skip-to-content link
- ARIA roles: `tablist`, `tab`, `tabpanel`, `dialog`
- `aria-selected` on tab buttons
- `aria-expanded` on settings trigger
- `focus-visible` outlines on interactive elements
- `prefers-reduced-motion` respected
- Print stylesheet (hides chrome, shows content)