"""Tests for the repository wizard flow and multi-source generation.

Covers:
- Source validation (factory.validate_repo_source)
- Wizard state management (WizardState, WizardRepository)
- Wizard API endpoints (web/server.py /api/wizard/*)
- Multi-repo settings generation
- Error handling and edge cases
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from releasepilot.web.server import create_app

# ── Wizard API Endpoint Tests ──────────────────────────────────────────────


@pytest.fixture()
def wizard_client():
    """Create a test client with isolated config."""
    app = create_app({"repo_path": ".", "app_name": "Test"})
    return TestClient(app)


class TestWizardReleaseRange:
    """PUT /api/wizard/release-range"""

    """GIVEN a scenario for set range"""

    def test_set_range(self, wizard_client):
        """WHEN the test exercises set range"""
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={
                "from_ref": "v1.0.0",
                "to_ref": "v2.0.0",
                "branch": "main",
            },
        )
        """THEN the expected behavior for set range is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["release_range"]["from_ref"] == "v1.0.0"
        assert data["release_range"]["to_ref"] == "v2.0.0"
        assert data["release_range"]["branch"] == "main"
        assert data["step"] == "audience"

    """GIVEN a scenario for set date range"""

    def test_set_date_range(self, wizard_client):
        """WHEN the test exercises set date range"""
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "2025-01-01"},
        )
        """THEN the expected behavior for set date range is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["release_range"]["since_date"] == "2025-01-01"

    """GIVEN a scenario for invalid date"""

    def test_invalid_date(self, wizard_client):
        """WHEN the test exercises invalid date"""
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "not-a-date"},
        )
        """THEN the expected behavior for invalid date is observed"""
        assert r.status_code == 400

    """GIVEN a scenario for valid date format"""

    def test_valid_date_format(self, wizard_client):
        """WHEN the test exercises valid date format"""
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "2025-12-31"},
        )
        """THEN the expected behavior for valid date format is observed"""
        assert r.status_code == 200


class TestWizardOptions:
    """PUT /api/wizard/options"""

    """GIVEN a scenario for set options"""

    def test_set_options(self, wizard_client):
        """WHEN the test exercises set options"""
        r = wizard_client.put(
            "/api/wizard/options",
            json={
                "audience": "executive",
                "output_format": "pdf",
                "language": "de",
                "app_name": "MyProduct",
                "version": "3.0.0",
                "title": "Sprint Release",
            },
        )
        """THEN the expected behavior for set options is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["options"]["audience"] == "executive"
        assert data["options"]["output_format"] == "pdf"
        assert data["options"]["language"] == "de"
        assert data["options"]["app_name"] == "MyProduct"
        assert data["options"]["version"] == "3.0.0"
        assert data["options"]["title"] == "Sprint Release"
        assert data["step"] == "review"

    """GIVEN a scenario for invalid audience"""

    def test_invalid_audience(self, wizard_client):
        """WHEN the test exercises invalid audience"""
        r = wizard_client.put(
            "/api/wizard/options",
            json={"audience": "invalid"},
        )
        """THEN the expected behavior for invalid audience is observed"""
        assert r.status_code == 400

    """GIVEN a scenario for invalid format"""

    def test_invalid_format(self, wizard_client):
        """WHEN the test exercises invalid format"""
        r = wizard_client.put(
            "/api/wizard/options",
            json={"output_format": "invalid"},
        )
        """THEN the expected behavior for invalid format is observed"""
        assert r.status_code == 400

    """GIVEN a scenario for invalid language"""

    def test_invalid_language(self, wizard_client):
        """WHEN the test exercises invalid language"""
        r = wizard_client.put(
            "/api/wizard/options",
            json={"language": "xx"},
        )
        """THEN the expected behavior for invalid language is observed"""
        assert r.status_code == 400

    """GIVEN Only updating some fields should work"""

    def test_partial_update(self, wizard_client):
        """WHEN the test exercises partial update"""
        r = wizard_client.put(
            "/api/wizard/options",
            json={"audience": "summary"},
        )
        """THEN the expected behavior for partial update is observed"""
        assert r.status_code == 200
        assert r.json()["options"]["audience"] == "summary"
        # Defaults preserved
        assert r.json()["options"]["output_format"] == "markdown"


class TestWizardGenerate:
    """POST /api/wizard/generate"""

    """GIVEN a scenario for generate no repos"""

    def test_generate_no_repos(self, wizard_client):
        """WHEN the test exercises generate no repos"""
        r = wizard_client.post("/api/wizard/generate")
        """THEN the expected behavior for generate no repos is observed"""
        assert r.status_code == 400
        assert "no repositories" in r.json()["error"].lower()

    """GIVEN After adding a repo and configuring, generation should start"""

    def test_generate_starts_generation(self, wizard_client):
        # Add a local repo
        """WHEN the test exercises generate starts generation"""
        wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/repo",
                "token": "ghp_test",
                "app_label": "MyApp",
            },
        )
        # Set release range
        wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "2025-01-01"},
        )

        r = wizard_client.post("/api/wizard/generate")
        """THEN the expected behavior for generate starts generation is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["message"] == "Generation started"
        assert data["repository_count"] == 1


class TestWizardFullFlow:
    """Integration tests for the complete wizard flow."""

    """GIVEN Complete wizard flow: source type → add repo → range → options → state check"""

    def test_full_flow_single_remote(self, wizard_client):
        # Step 1: Source type
        """WHEN the test exercises full flow single remote"""
        r = wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "remote"},
        )
        """THEN the expected behavior for full flow single remote is observed"""
        assert r.json()["step"] == "repositories"

        # Step 2: Add repository
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/frontend",
                "token": "ghp_test",
                "app_label": "Frontend",
            },
        )
        assert r.json()["repository_count"] == 1

        # Step 3: Release range
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "2025-01-01", "branch": "main"},
        )
        assert r.json()["step"] == "audience"

        # Step 4: Options
        r = wizard_client.put(
            "/api/wizard/options",
            json={"audience": "changelog", "language": "en"},
        )
        assert r.json()["step"] == "review"

        # Verify final state
        r = wizard_client.get("/api/wizard/state")
        data = r.json()
        assert data["repository_count"] == 1
        assert data["release_range"]["since_date"] == "2025-01-01"
        assert data["options"]["audience"] == "changelog"

    """GIVEN Multi-repo wizard flow with two GitHub repositories"""

    def test_full_flow_multi_repo(self, wizard_client):
        """WHEN the test exercises full flow multi repo"""
        wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "remote"},
        )

        # Add first repo
        wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/frontend",
                "token": "ghp_test",
                "app_label": "Frontend",
            },
        )

        # Add second repo
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/backend",
                "token": "ghp_test",
                "app_label": "Backend",
            },
        )
        """THEN the expected behavior for full flow multi repo is observed"""
        assert r.json()["repository_count"] == 2

        # Range + options
        wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "2025-01-01"},
        )
        wizard_client.put(
            "/api/wizard/options",
            json={"audience": "summary", "title": "Sprint 42"},
        )

        # Verify state
        r = wizard_client.get("/api/wizard/state")
        data = r.json()
        assert data["repository_count"] == 2
        assert data["options"]["title"] == "Sprint 42"

        # List repositories
        r = wizard_client.get("/api/wizard/repositories")
        repos = r.json()["repositories"]
        assert len(repos) == 2
        labels = [r["app_label"] for r in repos]
        assert "Frontend" in labels
        assert "Backend" in labels

    """GIVEN Wizard reset should clear all state"""

    def test_flow_reset_and_restart(self, wizard_client):
        # Build some state
        """WHEN the test exercises flow reset and restart"""
        wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "remote"},
        )
        wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/repo",
                "token": "ghp_test",
            },
        )

        # Reset
        r = wizard_client.post("/api/wizard/reset")
        """THEN the expected behavior for flow reset and restart is observed"""
        assert r.json()["step"] == "source_type"
        assert r.json()["repository_count"] == 0

        # Verify repos are gone
        r = wizard_client.get("/api/wizard/repositories")
        assert r.json()["repository_count"] == 0

    """GIVEN Remove a repo and add a different one"""

    def test_remove_and_re_add(self, wizard_client):
        """WHEN the test exercises remove and re add"""
        r1 = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/old-repo",
                "token": "ghp_test",
            },
        )
        repo_id = r1.json()["repository"]["id"]

        wizard_client.delete(f"/api/wizard/repositories/{repo_id}")

        r2 = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/new-repo",
                "token": "ghp_test",
            },
        )
        """THEN the expected behavior for remove and re add is observed"""
        assert r2.json()["repository_count"] == 1
        assert r2.json()["repository"]["owner"] == "org"
        assert r2.json()["repository"]["repo"] == "new-repo"


class TestBuildSettingsMultiRepo:
    """Test _build_settings_from_config with multi_repo_sources."""

    """GIVEN Multi-repo sources should be passed through to Settings"""

    def test_multi_repo_sources_passthrough(self):
        """WHEN the test exercises multi repo sources passthrough"""
        from releasepilot.web.server import _build_settings_from_config

        config = {
            "since_date": "2025-01-01",
            "multi_repo_sources": [
                {
                    "url": "https://github.com/a/b",
                    "provider": "github",
                    "token": "ghp_test",
                    "app_label": "Frontend",
                },
                {
                    "url": "https://github.com/a/c",
                    "provider": "github",
                    "token": "ghp_test",
                    "app_label": "Backend",
                },
            ],
        }
        settings = _build_settings_from_config(config)
        """THEN the expected behavior for multi repo sources passthrough is observed"""
        assert settings.is_multi_repo is True
        assert len(settings.multi_repo_sources) == 2
        assert settings.multi_repo_sources[0]["app_label"] == "Frontend"
        assert settings.multi_repo_sources[1]["app_label"] == "Backend"

    """GIVEN Empty multi_repo_sources should not activate multi-repo mode"""

    def test_empty_multi_repo_sources(self):
        """WHEN the test exercises empty multi repo sources"""
        from releasepilot.web.server import _build_settings_from_config

        config = {"since_date": "2025-01-01", "multi_repo_sources": []}
        settings = _build_settings_from_config(config)
        """THEN the expected behavior for empty multi repo sources is observed"""
        assert settings.is_multi_repo is False

    """GIVEN Single GitHub source should not use multi-repo mode"""

    def test_single_github_source(self):
        """WHEN the test exercises single github source"""
        from releasepilot.web.server import _build_settings_from_config

        config = {
            "since_date": "2025-01-01",
            "github_owner": "org",
            "github_repo": "project",
            "github_token": "ghp_test",
        }
        settings = _build_settings_from_config(config)
        """THEN the expected behavior for single github source is observed"""
        assert settings.is_github_source is True
        assert settings.is_multi_repo is False
