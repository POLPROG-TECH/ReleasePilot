# Troubleshooting

Common issues and their solutions when working with ReleasePilot.

---

## SSL certificate errors (`CERTIFICATE_VERIFY_FAILED`)

**Symptom:** ReleasePilot fails with `SSL: CERTIFICATE_VERIFY_FAILED` or `ssl_error` when connecting to GitLab.

**Cause:** Corporate proxy (Zscaler, Netskope, etc.) intercepts HTTPS and uses its own CA certificate that Python doesn't trust.

**Fix - find and export your corporate CA bundle:**

<details>
<summary><b>macOS / Linux</b></summary>

```bash
# macOS - export system certificates (includes Zscaler CA)
security find-certificate -a -p \
  /Library/Keychains/System.keychain \
  /System/Library/Keychains/SystemRootCertificates.keychain \
  > ~/combined-ca-bundle.pem

# On Linux, the CA bundle is usually already available:
#   /etc/ssl/certs/ca-certificates.crt          (Debian/Ubuntu)
#   /etc/pki/tls/certs/ca-bundle.crt            (RHEL/Fedora)
# If your proxy adds its own CA, ask your IT department for the .pem file
# and append it: cat corporate-ca.pem >> ~/combined-ca-bundle.pem

# Tell Python to use it (add to ~/.zshrc or ~/.bashrc to persist)
export SSL_CERT_FILE=~/combined-ca-bundle.pem
export REQUESTS_CA_BUNDLE=~/combined-ca-bundle.pem

# Now ReleasePilot works
releasepilot inspect --remote https://gitlab.example.com/group/project
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

# 3. Now ReleasePilot works
releasepilot inspect --remote https://gitlab.example.com/group/project
```

> **Tip:** To make environment variables permanent on Windows, use `[System.Environment]::SetEnvironmentVariable("SSL_CERT_FILE", "$env:USERPROFILE\corporate-ca-bundle.pem", "User")` or set them via System Properties → Environment Variables.
</details>

**Quick check - is your venv working?**

```bash
pip install --dry-run requests 2>&1 | head -5
# Should show "Would install …" - not an SSL error
```

> **How it works:** ReleasePilot's SSL resolution order is: `SSL_CERT_FILE` env → `certifi` package → macOS system keychain (automatic) → Python default. In most corporate environments, setting `SSL_CERT_FILE` is the most reliable fix.

---

## SSL errors during `pip install`

**Symptom:** `pip install -e ".[dev]"` fails with `SSL: CERTIFICATE_VERIFY_FAILED` or similar.

**Cause:** Same corporate proxy issue - `pip` also needs the CA bundle.

**Fix:** Set `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` before running pip (see above), then:

```bash
pip install --upgrade pip setuptools
pip install -e ".[dev]"
```

---

## GitLab repositories return 404 (private repos)

**Symptom:** `[not_found] Resource not found` for repos that definitely exist.

**Cause:** GitLab returns 404 (not 401/403) for private repositories when the request is unauthenticated. This is by design - GitLab hides private repos from anonymous users.

**Fix - provide a GitLab Personal Access Token:**

Option A - **environment variable:**

```bash
export RELEASEPILOT_GITLAB_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx"
releasepilot inspect --remote https://gitlab.example.com/group/project
```

Option B - **config file** (`.releasepilot.json`):

```json
{
  "gitlab_token": "glpat-xxxxxxxxxxxxxxxxxxxx"
}
```

Option C - **via the Web Dashboard** (recommended for interactive use):

1. Start `releasepilot serve`
2. Enter the GitLab token in the configuration panel
3. The token is stored in the browser's `localStorage` and restored automatically

> **How to create a token:** GitLab → Settings → Access Tokens → create with `read_api` scope (Reporter role or higher on the projects).

---

## Wrong GitLab hostname - all repos fail

**Symptom:** All repos return `not_found` or `network_error`, but your token is correct.

**Cause:** The GitLab hostname in your config doesn't match the actual server.

**Fix - verify the correct hostname from a local clone:**

```bash
cd your-project
git remote -v
# origin  https://gitlab.actual-host.com/group/project.git (fetch)
#                  ^^^^^^^^^^^^^^^^^^^^^^^^
#                  This is the correct hostname
```

Then update the `gitlab_url` in your config or environment:

```bash
export RELEASEPILOT_GITLAB_URL="https://gitlab.actual-host.com"
```

---

## Transient server errors (502/503/504)

ReleasePilot automatically retries transient GitLab server errors (502, 503, 504) up to 2 times with exponential back-off. No configuration is needed.

If the GitLab instance is persistently returning 5xx errors, check its status page or contact your GitLab administrator.

---

## Proxy configuration

ReleasePilot uses Python's `urllib`, which automatically respects standard proxy environment variables:

```bash
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
export NO_PROXY=localhost,127.0.0.1,.internal.example.com
```

No additional ReleasePilot configuration is needed.

---

## Server won't start - `address already in use`

```bash
# Find and kill whatever is using the port
lsof -i :8082 -t | xargs kill -9    # macOS / Linux

# Or use a different port
releasepilot serve --port 9082
```
