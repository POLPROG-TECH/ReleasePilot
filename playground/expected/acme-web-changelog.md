# Acme Web

## Changes since 2026-01-15

### 📊 Release Metrics

| Metric | Value |
|--------|-------|
| Total Changes | 13 |
| Raw changes | 14 |
| Filtered out | 1 |
| Contributors | 1 |
| First commit | 2026-01-20 |
| Last commit | 2026-03-15 |
| Components | api, cache, export, i18n, notifications, payments, search, teams, upload, ux |

## 🔥 Highlights

- **Patch XSS vulnerability in comment rendering**

## 🔒 Security

- Patch XSS vulnerability in comment rendering

## ✨ New Features

- Add rate limiting middleware - `api`
- Add PDF export for reports - `export`
- Add push notification support - `notifications`
- Add full-text search with Elasticsearch - `search`
- Add team management and role-based access - `teams`

## 🐛 Bug Fixes

- Correct Polish date formatting - `i18n`
- Handle expired card retry logic - `payments`
- Handle large file uploads gracefully - `upload`

## ⚡ Performance

- Implement Redis caching layer - `cache`

## 📝 Documentation

- Add deployment runbook for v3.0

## ♻️ Refactoring

- Migrate from REST to GraphQL endpoints - `api`

## 📋 Other Changes

- Streamline onboarding wizard flow - `ux`

---
*13 changes in this release*

*Pipeline: 14 collected → 1 filtered → 0 deduplicated → 13 final*

*Generated using the free ReleasePilot tool, created by POLPROG · 2026-03-16 16:01 UTC · https://github.com/polprog-tech/ReleasePilot*

