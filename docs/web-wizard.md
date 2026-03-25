# Web Wizard — Release Note Generation

The ReleasePilot web wizard provides a guided, multi-step workflow for generating release notes. It supports both local and remote repositories, single and multi-repository modes, and includes built-in validation at every step.

## Wizard Flow

The wizard uses progressive disclosure — each step asks one focused question:

| Step | Name | Purpose |
|------|------|---------|
| 1 | **Source** | Choose Local or Remote repository mode |
| 2 | **Repositories** | Configure repository access and selection |
| 3 | **Scope** | Define the release range (date or ref-based) |
| 4 | **Audience** | Select who the release notes are for |
| 5 | **Format** | Choose the output format |
| 6 | **Review** | Review configuration summary |
| 7 | **Pipeline** | Processing / generation screen with progress indicator |
| 8 | **Preview & Export** | View, copy, and download the result |

## Source Modes

### Local Repository

Uses the git repository in the current working directory by default. The wizard auto-detects the repository name, branch, and version.

**Repository Mode options (local):**

- **Current Repository** — Use the single repository in the working directory (default)
- **Scan Directory** — Enter a directory path to discover all git repositories inside it. The wizard scans immediate subdirectories for `.git` folders and lets you select which repositories to include.

### Remote Repository

Connects to GitHub or GitLab repositories via their API. Requires:

- **Provider selection** — GitHub or GitLab
- **Access token** — context-dependent:
  - **GitHub:** Optional for public repositories, required for private repos. The wizard shows "Continue without token" for GitHub.
  - **GitLab:** Always required (personal or project access token with `read_api` scope)
- **GitLab URL** (GitLab only) — The base URL of your GitLab instance
- **Repository URL** — Enter the full URL to the repository

> **Note:** The repository URL input is always visible regardless of token validation state. You can enter repository URLs at any time. However, the "Inspect Repository" button requires a validated token. For GitHub public repos, you can skip token validation and proceed directly.

## Single vs. Multiple Repositories

### Remote Mode

After configuring authentication, you can choose:

- **Single Repository** — Generate release notes from one repository
- **Multiple Repositories** — Aggregate commits from multiple repositories under a shared scope

In multi-repository mode:
- Each repository is validated and added individually
- Duplicate URLs are rejected
- Up to 20 repositories are supported
- The release range/scope applies to all repositories
- Output groups commits by repository with clear provenance labels

### Local Mode (Directory Scan)

When using "Scan Directory" mode:
- Enter the path to a parent directory
- The wizard scans for subdirectories containing `.git` folders
- Select/deselect individual repositories from the discovered list
- All selected repositories share the same release scope

## Validation

The wizard enforces validation at every step. The **Next** button is disabled until the current step is valid.

### Step-by-Step Validation Rules

**Step 1 — Source:**
- Always valid (one option is always selected)

**Step 2 — Repositories:**

*Remote mode:*
- GitLab URL is required and must be a valid HTTP(S) URL
- **GitHub:** Access token is optional for public repositories — the wizard provides a "Continue without token" button. Token is still recommended for higher API rate limits and inspection.
- **GitLab:** Access token is always required and must be validated via the API
- Repository URL must match the expected format:
  - GitHub: `https://github.com/owner/repo`
  - GitLab: `https://gitlab.example.com/group/project`
- Multi-repo mode requires at least one repository to be added
- Duplicate repository URLs are rejected

*Local mode — Current Repository:*
- The current directory must be a valid git repository

*Local mode — Scan Directory:*
- Directory path is required
- Directory must be scanned (click "Scan")
- At least one repository must be selected from the scan results

**Step 3 — Scope:**
- Date mode: a date must be selected and cannot be in the future
- Ref mode: a starting reference (tag/branch/SHA) is required
- A live preview shows commit count, date span, and breaking changes as you configure the scope
- Changing the date, branch, or refs automatically refreshes the preview

**Steps 4–5 — Audience & Format:**
- Always valid (a default selection is always present)
- The Format step shows a context badge indicating which audience is selected and how many formats are available

**Step 6 — Review:**
- Displays a summary of all selections (source, repos, scope, audience, format)
- Provides edit buttons to jump back to any previous step
- Contains the "Generate Release Notes" button

**Step 7 — Pipeline:**
- Dedicated processing screen with progress spinner
- Shows success/failure results after generation completes
- On success, offers navigation to Preview & Export

### Inline Error Messages

Validation errors appear directly under the relevant input field. Invalid fields are visually highlighted with a red border. The step indicator in the stepper bar shows an error state if advancement is attempted with invalid data.

## SSL / Corporate Network Compatibility

### Verify SSL Toggle

The wizard includes a "Verify SSL certificates" toggle in the authentication section. This controls whether SSL certificate verification is performed when connecting to remote repositories.

**When to disable:**
- Self-signed certificates on internal GitLab instances
- Corporate proxy (Zscaler, Netskope) intercepting TLS
- Development environments with custom CA chains

**Default:** Enabled (secure by default)

### SSL Resolution Order

When SSL verification is enabled, ReleasePilot resolves certificates in this order:

1. `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE` environment variable
2. `certifi` package (if installed)
3. macOS system keychain (including corporate CAs)
4. Python default SSL context

### Proxy Support

ReleasePilot uses Python's `urllib`, which automatically respects standard proxy environment variables:

- `HTTP_PROXY` / `http_proxy`
- `HTTPS_PROXY` / `https_proxy`
- `NO_PROXY` / `no_proxy`

No additional proxy configuration is needed in the wizard.

### Configuration File

SSL verify can also be configured in `.releasepilot.json`:

```json
{
  "gitlab_ssl_verify": false,
  "github_ssl_verify": false
}
```

Both `snake_case` and `kebab-case` keys are supported (`gitlab-ssl-verify`).

## Authentication

### GitHub

- Supports personal access tokens (classic or fine-grained)
- Token needs `repo` read access (or `contents:read` for fine-grained)
- **Token is optional for public repositories** — if the repository is publicly accessible, ReleasePilot can collect commits without authentication
- **Token is required for private repositories** — authentication is enforced when the target repository requires it
- The wizard UI clearly indicates when a token is optional vs required based on the selected provider
- Set via the wizard UI, `GITHUB_TOKEN` environment variable, or config file
- Without a token, GitHub API rate limits are lower (60 requests/hour vs 5,000 authenticated)

> **Tip:** Even for public repositories, providing a token increases API rate limits and enables repository inspection features.

### GitLab

- Requires a personal or project access token (always required — GitLab does not support unauthenticated API access for most endpoints)
- Token needs `read_api` scope
- The GitLab instance URL must be provided for self-hosted instances
- Set via the wizard UI, `RELEASEPILOT_GITLAB_TOKEN` env var, or config file

## Keyboard Navigation

All wizard options support keyboard navigation:
- `Tab` to move between interactive elements
- `Enter` to select an option
- The stepper bar shows the current step and completed steps

## Internationalization

The wizard UI is fully localized. All labels, validation messages, button texts, section titles, helper texts, and status messages use translation keys resolved at runtime. Supported languages:

- English (en), Polish (pl), German (de), French (fr), Spanish (es), Italian (it), Portuguese (pt), Dutch (nl), Ukrainian (uk), Czech (cs)

The language can be changed via the Settings panel or during the Scope step of the wizard. All wizard screens — including validation error messages, scope banners, review summaries, and pipeline status — adapt to the selected language.

## API Endpoints

The wizard uses these API endpoints:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/wizard/state` | Get current wizard state |
| POST | `/api/wizard/reset` | Reset wizard to initial state |
| PUT | `/api/wizard/source-type` | Set source type (local/remote) |
| POST | `/api/wizard/repositories` | Add a repository |
| DELETE | `/api/wizard/repositories/{id}` | Remove a repository |
| GET | `/api/wizard/repositories` | List configured repositories |
| PUT | `/api/wizard/release-range` | Set the release range |
| PUT | `/api/wizard/options` | Set audience, format, language |
| POST | `/api/wizard/generate` | Trigger generation |
| POST | `/api/wizard/validate-url` | Validate a repository URL |
| POST | `/api/scan-directory` | Scan a local directory for git repositories |
| POST | `/api/github/validate` | Validate GitHub token |
| POST | `/api/gitlab/validate` | Validate GitLab token |

## Troubleshooting

### Token validation fails

- Verify the token has the correct scopes
- For GitLab, ensure the instance URL is correct and accessible
- Check if SSL verification needs to be disabled (corporate proxy)
- See [Troubleshooting Guide](troubleshooting.md) for SSL certificate errors

### "Not a git repository" error

- The web server must be started from a directory containing a `.git` folder
- Or switch to Remote mode to use repositories via URL

### No commits found

- Widen the date range or adjust the starting reference
- Verify the branch name is correct
- For remote repositories, ensure the token has access to the repository
