# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | ✅ Current release |

## Reporting a Vulnerability

If you discover a security vulnerability in ReleasePilot, please report it responsibly.

**Do not open a public issue.**

Instead, please email **releasepilot@polprog.tech** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge your report within **48 hours** and aim to provide a fix or mitigation within **7 days** for critical issues.

## Scope

Security concerns relevant to ReleasePilot include:

- **Command injection** via git commands or subprocess calls
- **Path traversal** in repository or file operations
- **Arbitrary code execution** through config files or input data
- **Dependency vulnerabilities** in third-party packages