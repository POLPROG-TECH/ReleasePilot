# ──────────────────────────────────────────────────────────────────────────────
# ReleasePilot — Remote Repository Examples (Dashboard)
# ──────────────────────────────────────────────────────────────────────────────
#
# These examples show how to use the ReleasePilot web dashboard to generate
# release notes from remote GitHub and GitLab repositories.
#
# ──────────────────────────────────────────────────────────────────────────────

# ─── Prerequisites ───────────────────────────────────────────────────────────
#
# 1. Install ReleasePilot:
#      pip install "releasepilot[all]"
#
# 2. Launch the dashboard:
#      releasepilot serve --repo .
#
# 3. Open the dashboard in your browser (default: http://localhost:8080)
#
# ──────────────────────────────────────────────────────────────────────────────

# ─── Single Remote Repository (GitHub) ───────────────────────────────────────
#
# In the wizard:
#   1. Source Type: Remote
#   2. Provider: GitHub
#   3. Repository Count: Single
#   4. Enter URL: https://github.com/POLPROG-TECH/ReleaseBoard
#   5. (Optional) Enter a GitHub token for private repos
#   6. Click "Inspect" to verify access
#   7. Choose scope (date-based recommended for remote)
#   8. Select audience and format
#   9. Generate
#
# The dashboard will fetch commits directly from the GitHub API and generate
# release notes from the remote repository — your local working directory
# is never used as a source.

# ─── Single Remote Repository (GitLab) ──────────────────────────────────────
#
# In the wizard:
#   1. Source Type: Remote
#   2. Provider: GitLab
#   3. Repository Count: Single
#   4. Enter URL: https://gitlab.com/mygroup/myproject
#   5. Enter a GitLab personal access token (required)
#   6. Click "Inspect" to verify access
#   7. Configure scope, audience, format
#   8. Generate
#
# GitLab requires a token with at least `read_api` scope.

# ─── Multi-Repository (GitHub) ──────────────────────────────────────────────
#
# In the wizard:
#   1. Source Type: Remote
#   2. Provider: GitHub
#   3. Repository Count: Multi
#   4. Add repositories one by one:
#        https://github.com/POLPROG-TECH/ReleasePilot
#        https://github.com/POLPROG-TECH/ReleaseBoard
#   5. (Optional) Set a custom label for each repository
#   6. Configure scope, audience, format
#   7. Generate
#
# The output will aggregate commits from all selected repositories.
# Each change item retains provenance (which repo it came from).

# ─── Organization Discovery (GitHub) ────────────────────────────────────────
#
# Instead of adding repositories one by one, enter an organization URL:
#
#   https://github.com/POLPROG-TECH
#   https://github.com/orgs/POLPROG-TECH/repositories
#
# The dashboard will:
#   1. Detect the organization URL
#   2. Fetch the list of repositories in that organization
#   3. Show a picker with checkboxes
#   4. Let you select which repositories to include
#   5. Add selected repositories to the multi-repo list
#
# This works with both organizations and personal accounts.

# ─── Group Discovery (GitLab) ───────────────────────────────────────────────
#
# Enter a GitLab group URL:
#
#   https://gitlab.com/mygroup
#
# The dashboard will enumerate projects under that group (including
# subgroups) and let you select which ones to include.
# Requires a token with group-level read access.

# ─── Environment Variables ──────────────────────────────────────────────────
#
# Tokens can also be provided via environment variables:
#
#   export RELEASEPILOT_GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
#   export RELEASEPILOT_GITLAB_TOKEN=glpat-xxxxxxxxxxxxx
#   export RELEASEPILOT_GITLAB_URL=https://gitlab.example.com
#
# When set, the dashboard will use these automatically.
