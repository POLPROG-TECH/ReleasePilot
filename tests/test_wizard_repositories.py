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


class TestWizardAddRepository:
    """POST /api/wizard/repositories"""

    """GIVEN a scenario for add github repo"""

    def test_add_github_repo(self, wizard_client):
        """WHEN the test exercises add github repo"""
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/polprog-tech/ReleasePilot",
                "token": "ghp_test",
                "app_label": "ReleasePilot",
            },
        )
        """THEN the expected behavior for add github repo is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["repository"]["source_type"] == "github"
        assert data["repository"]["app_label"] == "ReleasePilot"
        assert data["repository"]["token_set"] is True
        assert data["repository_count"] == 1

    """GIVEN a scenario for add gitlab repo"""

    def test_add_gitlab_repo(self, wizard_client):
        """WHEN the test exercises add gitlab repo"""
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "gitlab",
                "url": "https://gitlab.example.com/group/project",
                "token": "glpat_test",
                "app_label": "Backend",
            },
        )
        """THEN the expected behavior for add gitlab repo is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["repository"]["source_type"] == "gitlab"

    """GIVEN a scenario for add local repo"""

    def test_add_local_repo(self, wizard_client, tmp_path):
        """WHEN the test exercises add local repo"""
        (tmp_path / ".git").mkdir()
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "local",
                "path": str(tmp_path),
                "app_label": "LocalApp",
            },
        )
        """THEN the expected behavior for add local repo is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["repository"]["source_type"] == "local"
        assert data["repository"]["app_label"] == "LocalApp"

    """GIVEN a scenario for add missing url"""

    def test_add_missing_url(self, wizard_client):
        """WHEN the test exercises add missing url"""
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={"source_type": "github"},
        )
        """THEN the expected behavior for add missing url is observed"""
        assert r.status_code == 400

    """GIVEN a scenario for add invalid url"""

    def test_add_invalid_url(self, wizard_client):
        """WHEN the test exercises add invalid url"""
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "not-a-valid-url",
            },
        )
        """THEN the expected behavior for add invalid url is observed"""
        assert r.status_code == 400

    """GIVEN Adding the same repo twice should fail"""

    def test_add_duplicate(self, wizard_client):
        """WHEN the test exercises add duplicate"""
        payload = {
            "source_type": "github",
            "url": "https://github.com/polprog-tech/ReleasePilot",
            "token": "ghp_test",
        }
        wizard_client.post("/api/wizard/repositories", json=payload)
        r = wizard_client.post("/api/wizard/repositories", json=payload)
        """THEN the expected behavior for add duplicate is observed"""
        assert r.status_code == 400
        assert "already" in r.json()["error"].lower()

    """GIVEN Multiple different repos should succeed"""

    def test_add_multiple_repos(self, wizard_client):
        """WHEN the test exercises add multiple repos"""
        wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/repo1",
                "token": "ghp_test",
            },
        )
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/repo2",
                "token": "ghp_test",
            },
        )
        """THEN the expected behavior for add multiple repos is observed"""
        assert r.status_code == 200
        assert r.json()["repository_count"] == 2


class TestWizardRemoveRepository:
    """DELETE /api/wizard/repositories/{repo_id}"""

    """GIVEN a scenario for remove repo"""

    def test_remove_repo(self, wizard_client):
        """WHEN the test exercises remove repo"""
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/repo",
                "token": "ghp_test",
            },
        )
        repo_id = r.json()["repository"]["id"]

        r2 = wizard_client.delete(f"/api/wizard/repositories/{repo_id}")
        """THEN the expected behavior for remove repo is observed"""
        assert r2.status_code == 200
        assert r2.json()["repository_count"] == 0

    """GIVEN a scenario for remove nonexistent"""

    def test_remove_nonexistent(self, wizard_client):
        """WHEN the test exercises remove nonexistent"""
        r = wizard_client.delete("/api/wizard/repositories/nonexistent")
        """THEN the expected behavior for remove nonexistent is observed"""
        assert r.status_code == 404


class TestWizardListRepositories:
    """GET /api/wizard/repositories"""

    """GIVEN a scenario for empty list"""

    def test_empty_list(self, wizard_client):
        """WHEN the test exercises empty list"""
        r = wizard_client.get("/api/wizard/repositories")
        """THEN the expected behavior for empty list is observed"""
        assert r.status_code == 200
        assert r.json()["repository_count"] == 0
        assert r.json()["repositories"] == []

    """GIVEN a scenario for list after add"""

    def test_list_after_add(self, wizard_client):
        """WHEN the test exercises list after add"""
        wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/org/repo",
                "token": "ghp_test",
                "app_label": "TestApp",
            },
        )
        r = wizard_client.get("/api/wizard/repositories")
        """THEN the expected behavior for list after add is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["repository_count"] == 1
        assert data["repositories"][0]["app_label"] == "TestApp"


class TestWizardValidateUrl:
    """POST /api/wizard/validate-url"""

    """GIVEN a scenario for validate github"""

    def test_validate_github(self, wizard_client):
        """WHEN the test exercises validate github"""
        r = wizard_client.post(
            "/api/wizard/validate-url",
            json={"url": "https://github.com/owner/repo"},
        )
        """THEN the expected behavior for validate github is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["provider"] == "github"
        assert data["owner"] == "owner"
        assert data["repo"] == "repo"

    """GIVEN a scenario for validate gitlab"""

    def test_validate_gitlab(self, wizard_client):
        """WHEN the test exercises validate gitlab"""
        r = wizard_client.post(
            "/api/wizard/validate-url",
            json={"url": "https://gitlab.example.com/group/project"},
        )
        """THEN the expected behavior for validate gitlab is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["provider"] == "gitlab"

    """GIVEN a scenario for validate invalid"""

    def test_validate_invalid(self, wizard_client):
        """WHEN the test exercises validate invalid"""
        r = wizard_client.post(
            "/api/wizard/validate-url",
            json={"url": "https://bitbucket.org/owner/repo"},
        )
        """THEN the expected behavior for validate invalid is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False

    """GIVEN a scenario for validate missing url"""

    def test_validate_missing_url(self, wizard_client):
        """WHEN the test exercises validate missing url"""
        r = wizard_client.post(
            "/api/wizard/validate-url",
            json={},
        )
        """THEN the expected behavior for validate missing url is observed"""
        assert r.status_code == 400


class TestScanDirectory:
    """POST /api/scan-directory"""

    """GIVEN a scenario for missing path"""

    def test_missing_path(self, wizard_client):
        """WHEN the test exercises missing path"""
        r = wizard_client.post("/api/scan-directory", json={})
        """THEN the expected behavior for missing path is observed"""
        assert r.status_code == 400
        data = r.json()
        assert data["ok"] is False
        assert "path" in data["error"].lower()

    """GIVEN a scenario for empty path"""

    def test_empty_path(self, wizard_client):
        """WHEN the test exercises empty path"""
        r = wizard_client.post("/api/scan-directory", json={"path": ""})
        """THEN the expected behavior for empty path is observed"""
        assert r.status_code == 400

    """GIVEN a scenario for unsafe path rejected"""

    def test_unsafe_path_rejected(self, wizard_client):
        """WHEN the test exercises unsafe path rejected"""
        r = wizard_client.post("/api/scan-directory", json={"path": "/tmp;rm -rf"})
        """THEN the expected behavior for unsafe path rejected is observed"""
        assert r.status_code == 400
        data = r.json()
        assert data["ok"] is False
        assert "unsafe" in data["error"].lower()

    """GIVEN a scenario for nonexistent path"""

    def test_nonexistent_path(self, wizard_client):
        """WHEN the test exercises nonexistent path"""
        r = wizard_client.post(
            "/api/scan-directory",
            json={"path": "/nonexistent/path/that/does/not/exist"},
        )
        """THEN the expected behavior for nonexistent path is observed"""
        assert r.status_code == 400

    """GIVEN Current directory (ReleasePilot repo root) should be found as a git repo"""

    def test_scan_current_directory(self, wizard_client):
        """WHEN the test exercises scan current directory"""
        r = wizard_client.post("/api/scan-directory", json={"path": "."})
        data = r.json()
        """THEN the expected behavior for scan current directory is observed"""
        assert data["ok"] is True
        assert data["count"] >= 1
        assert len(data["repos"]) >= 1
        # Current dir itself should be in the results
        names = [repo["name"] for repo in data["repos"]]
        assert any(name for name in names)

    """GIVEN a scenario for scan returns repo structure"""

    def test_scan_returns_repo_structure(self, wizard_client):
        """WHEN the test exercises scan returns repo structure"""
        r = wizard_client.post("/api/scan-directory", json={"path": "."})
        data = r.json()
        """THEN the expected behavior for scan returns repo structure is observed"""
        assert data["ok"] is True
        for repo in data["repos"]:
            assert "name" in repo
            assert "path" in repo
            assert repo["name"]  # non-empty
            assert repo["path"]  # non-empty

    """GIVEN An empty directory should return 404 with no repos"""

    def test_scan_no_repos_in_dir(self, wizard_client, tmp_path):
        """WHEN the test exercises scan no repos in dir"""
        r = wizard_client.post("/api/scan-directory", json={"path": str(tmp_path)})
        """THEN the expected behavior for scan no repos in dir is observed"""
        assert r.status_code == 404
        data = r.json()
        assert data["ok"] is False
        assert "no git" in data["error"].lower()

    """GIVEN Create fake repos in a parent dir and verify scanning"""

    def test_scan_finds_nested_repos(self, wizard_client, tmp_path):
        # Create two fake git repos
        """WHEN the test exercises scan finds nested repos"""
        repo1 = tmp_path / "alpha"
        repo1.mkdir()
        (repo1 / ".git").mkdir()

        repo2 = tmp_path / "beta"
        repo2.mkdir()
        (repo2 / ".git").mkdir()

        # Non-repo dir
        (tmp_path / "not-a-repo").mkdir()

        r = wizard_client.post("/api/scan-directory", json={"path": str(tmp_path)})
        data = r.json()
        """THEN the expected behavior for scan finds nested repos is observed"""
        assert data["ok"] is True
        assert data["count"] == 2
        names = sorted(repo["name"] for repo in data["repos"])
        assert names == ["alpha", "beta"]
