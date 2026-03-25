"""Tests for the repository wizard flow and multi-source generation.

Covers:
- Source validation (factory.validate_repo_source)
- Wizard state management (WizardState, WizardRepository)
- Wizard API endpoints (web/server.py /api/wizard/*)
- Multi-repo settings generation
- Error handling and edge cases
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from releasepilot.sources.factory import (
    detect_provider,
    validate_repo_source,
)
from releasepilot.web.server import create_app
from releasepilot.web.state import (
    AppState,
    WizardRepository,
    WizardState,
    WizardStep,
)

# ── Source Validation Tests ─────────────────────────────────────────────────


class TestDetectProvider:
    """Tests for detect_provider()."""

    def test_github_url(self):
        assert detect_provider("https://github.com/owner/repo") == "github"

    def test_github_with_www(self):
        assert detect_provider("https://www.github.com/owner/repo") == "github"

    def test_gitlab_url(self):
        assert detect_provider("https://gitlab.com/group/project") == "gitlab"

    def test_self_hosted_gitlab(self):
        assert detect_provider("https://gitlab.example.com/g/p") == "gitlab"

    def test_unknown_url(self):
        assert detect_provider("https://bitbucket.org/owner/repo") == "unknown"

    def test_case_insensitive(self):
        assert detect_provider("https://GITHUB.COM/owner/repo") == "github"


class TestValidateRepoSource:
    """Tests for validate_repo_source()."""

    def test_empty_input(self):
        result = validate_repo_source("")
        assert not result.valid
        assert "required" in result.error.lower()

    def test_whitespace_only(self):
        result = validate_repo_source("   ")
        assert not result.valid

    def test_github_valid_url(self):
        result = validate_repo_source("https://github.com/polprog-tech/ReleasePilot")
        assert result.valid
        assert result.provider == "github"
        assert result.owner == "polprog-tech"
        assert result.repo == "ReleasePilot"
        assert result.display_name == "polprog-tech/ReleasePilot"

    def test_github_with_git_suffix(self):
        result = validate_repo_source("https://github.com/owner/repo.git")
        assert result.valid
        assert result.provider == "github"
        assert result.repo == "repo"

    def test_github_with_trailing_slash(self):
        result = validate_repo_source("https://github.com/owner/repo/")
        assert result.valid
        assert result.provider == "github"

    def test_github_invalid_format(self):
        """Single-segment GitHub URL is now detected as org/user page."""
        result = validate_repo_source("https://github.com/onlyowner")
        assert result.valid
        assert result.provider == "github"
        assert result.is_org is True
        assert result.org_name == "onlyowner"

    def test_github_token_required(self):
        """When no token is provided and no env var, requires_token should be True."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RELEASEPILOT_GITHUB_TOKEN", None)
            result = validate_repo_source(
                "https://github.com/owner/repo",
                token="",
            )
            assert result.valid
            assert result.requires_token is True

    def test_github_token_provided(self):
        result = validate_repo_source(
            "https://github.com/owner/repo",
            token="ghp_test123",
        )
        assert result.valid
        assert result.requires_token is False

    def test_gitlab_valid_url(self):
        result = validate_repo_source("https://gitlab.example.com/group/project")
        assert result.valid
        assert result.provider == "gitlab"
        assert result.project_path == "group/project"
        assert result.owner == "group"
        assert result.repo == "project"

    def test_gitlab_nested_groups(self):
        result = validate_repo_source("https://gitlab.example.com/org/team/sub/project")
        assert result.valid
        assert result.project_path == "org/team/sub/project"
        assert result.owner == "org/team/sub"
        assert result.repo == "project"

    def test_gitlab_with_git_suffix(self):
        result = validate_repo_source("https://gitlab.example.com/group/project.git")
        assert result.valid
        assert result.project_path == "group/project"

    def test_gitlab_no_path(self):
        result = validate_repo_source("https://gitlab.example.com/")
        assert not result.valid
        assert result.provider == "gitlab"

    def test_local_path_nonexistent(self):
        result = validate_repo_source("/tmp/nonexistent-repo-12345")
        assert not result.valid
        assert result.provider == "local"
        assert "not exist" in result.error.lower() or "does not exist" in result.error.lower()

    def test_local_path_not_git(self, tmp_path):
        """A real directory but not a git repo."""
        result = validate_repo_source(str(tmp_path))
        assert not result.valid
        assert "git" in result.error.lower()

    def test_local_path_is_git(self, tmp_path):
        """A real directory with .git subdirectory."""
        (tmp_path / ".git").mkdir()
        result = validate_repo_source(str(tmp_path))
        assert result.valid
        assert result.provider == "local"
        assert result.source_type == "local"

    def test_unknown_provider(self):
        result = validate_repo_source("https://bitbucket.org/owner/repo")
        assert not result.valid
        assert result.provider == "unknown"

    def test_custom_app_label(self):
        result = validate_repo_source(
            "https://github.com/owner/repo",
            app_label="MyApp",
        )
        assert result.valid
        assert result.display_name == "MyApp"

    def test_explicit_provider_override(self):
        result = validate_repo_source(
            "https://custom-gitlab.internal/group/project",
            provider="gitlab",
        )
        assert result.valid
        assert result.provider == "gitlab"


# ── Wizard State Tests ──────────────────────────────────────────────────────


class TestWizardRepository:
    """Tests for WizardRepository dataclass."""

    def test_display_name_github(self):
        repo = WizardRepository(source_type="github", owner="org", repo="project")
        assert repo.display_name == "org/project"

    def test_display_name_gitlab(self):
        repo = WizardRepository(source_type="gitlab", project_path="group/sub/proj")
        assert repo.display_name == "group/sub/proj"

    def test_display_name_custom_label(self):
        repo = WizardRepository(source_type="github", owner="org", repo="proj", app_label="MyApp")
        assert repo.display_name == "MyApp"

    def test_display_name_local(self):
        repo = WizardRepository(source_type="local", url="/path/to/repo")
        assert repo.display_name == "/path/to/repo"

    def test_requires_token_github_no_token(self):
        repo = WizardRepository(source_type="github", owner="o", repo="r")
        assert repo.requires_token is True

    def test_requires_token_github_with_token(self):
        repo = WizardRepository(source_type="github", owner="o", repo="r", token="ghp_test")
        assert repo.requires_token is False

    def test_requires_token_local(self):
        repo = WizardRepository(source_type="local", url="/path")
        assert repo.requires_token is False

    def test_to_dict_masks_token(self):
        repo = WizardRepository(
            source_type="github",
            owner="org",
            repo="proj",
            token="secret_token_value",
        )
        d = repo.to_dict()
        assert "token" not in d
        assert d["token_set"] is True

    def test_to_dict_no_token(self):
        repo = WizardRepository(source_type="local", url="/path")
        d = repo.to_dict()
        assert d["token_set"] is False

    def test_to_source_dict_local(self):
        repo = WizardRepository(source_type="local", url="/path/to/repo", app_label="MyApp")
        sd = repo.to_source_dict()
        assert sd["path"] == "/path/to/repo"
        assert sd["provider"] == "local"
        assert sd["app_label"] == "MyApp"

    def test_to_source_dict_github(self):
        repo = WizardRepository(
            source_type="github",
            url="https://github.com/a/b",
            owner="a",
            repo="b",
            token="ghp_123",
            app_label="Frontend",
        )
        sd = repo.to_source_dict()
        assert sd["url"] == "https://github.com/a/b"
        assert sd["provider"] == "github"
        assert sd["token"] == "ghp_123"
        assert sd["app_label"] == "Frontend"

    def test_to_source_dict_gitlab(self):
        repo = WizardRepository(
            source_type="gitlab",
            url="https://gitlab.example.com/g/p",
            project_path="g/p",
            token="glpat_abc",
            app_label="Backend",
        )
        sd = repo.to_source_dict()
        assert sd["url"] == "https://gitlab.example.com/g/p"
        assert sd["provider"] == "gitlab"
        assert sd["token"] == "glpat_abc"


class TestWizardState:
    """Tests for WizardState management."""

    def test_initial_state(self):
        ws = WizardState()
        assert ws.step == WizardStep.SOURCE_TYPE
        assert ws.source_type == ""
        assert ws.repositories == []
        assert ws.to_ref == "HEAD"
        assert ws.audience == "changelog"
        assert ws.output_format == "markdown"

    def test_add_repository(self):
        ws = WizardState()
        repo = WizardRepository(
            source_type="github",
            url="https://github.com/a/b",
            owner="a",
            repo="b",
        )
        err = ws.add_repository(repo)
        assert err is None
        assert len(ws.repositories) == 1
        assert ws.repositories[0].id  # auto-assigned

    def test_add_duplicate_rejected(self):
        ws = WizardState()
        repo1 = WizardRepository(source_type="github", url="https://github.com/a/b")
        repo2 = WizardRepository(source_type="github", url="https://github.com/a/b")
        ws.add_repository(repo1)
        err = ws.add_repository(repo2)
        assert err is not None
        assert "already added" in err.lower()
        assert len(ws.repositories) == 1

    def test_add_max_repositories(self):
        ws = WizardState()
        for i in range(ws.MAX_REPOSITORIES):
            repo = WizardRepository(
                source_type="github",
                url=f"https://github.com/org/repo{i}",
            )
            assert ws.add_repository(repo) is None

        extra = WizardRepository(
            source_type="github",
            url="https://github.com/org/extra",
        )
        err = ws.add_repository(extra)
        assert err is not None
        assert "maximum" in err.lower()

    def test_remove_repository(self):
        ws = WizardState()
        repo = WizardRepository(
            id="test-id",
            source_type="local",
            url="/path",
        )
        ws.add_repository(repo)
        assert ws.remove_repository("test-id") is True
        assert len(ws.repositories) == 0

    def test_remove_nonexistent(self):
        ws = WizardState()
        assert ws.remove_repository("nonexistent") is False

    def test_get_repository(self):
        ws = WizardState()
        repo = WizardRepository(id="test-id", source_type="local", url="/path")
        ws.add_repository(repo)
        found = ws.get_repository("test-id")
        assert found is not None
        assert found.id == "test-id"

    def test_get_nonexistent(self):
        ws = WizardState()
        assert ws.get_repository("missing") is None

    def test_to_dict(self):
        ws = WizardState()
        ws.source_type = "remote"
        ws.audience = "executive"
        d = ws.to_dict()
        assert d["source_type"] == "remote"
        assert d["options"]["audience"] == "executive"
        assert d["repository_count"] == 0
        assert "session_id" in d

    def test_to_generation_config_single_local(self):
        ws = WizardState()
        ws.since_date = "2025-01-01"
        ws.branch = "main"
        repo = WizardRepository(source_type="local", url="/path/to/repo")
        ws.add_repository(repo)

        cfg = ws.to_generation_config()
        assert cfg["repo_path"] == "/path/to/repo"
        assert cfg["since_date"] == "2025-01-01"
        assert cfg["branch"] == "main"
        assert "multi_repo_sources" not in cfg

    def test_to_generation_config_single_github(self):
        ws = WizardState()
        ws.from_ref = "v1.0"
        repo = WizardRepository(
            source_type="github",
            url="https://github.com/a/b",
            owner="a",
            repo="b",
            token="ghp_test",
        )
        ws.add_repository(repo)

        cfg = ws.to_generation_config()
        assert cfg["github_owner"] == "a"
        assert cfg["github_repo"] == "b"
        assert cfg["github_token"] == "ghp_test"
        assert "multi_repo_sources" not in cfg

    def test_to_generation_config_single_gitlab(self):
        ws = WizardState()
        repo = WizardRepository(
            source_type="gitlab",
            url="https://gitlab.example.com/g/p",
            project_path="g/p",
            token="glpat_abc",
        )
        ws.add_repository(repo)

        cfg = ws.to_generation_config()
        assert cfg["gitlab_project"] == "g/p"
        assert cfg["gitlab_token"] == "glpat_abc"
        assert cfg["gitlab_url"] == "https://gitlab.example.com"

    def test_to_generation_config_multi_repo(self):
        ws = WizardState()
        ws.since_date = "2025-01-01"
        ws.audience = "summary"

        repo1 = WizardRepository(
            source_type="github",
            url="https://github.com/a/b",
            owner="a",
            repo="b",
            token="ghp_1",
            app_label="Frontend",
        )
        repo2 = WizardRepository(
            source_type="github",
            url="https://github.com/a/c",
            owner="a",
            repo="c",
            token="ghp_2",
            app_label="Backend",
        )
        ws.add_repository(repo1)
        ws.add_repository(repo2)

        cfg = ws.to_generation_config()
        assert "multi_repo_sources" in cfg
        assert len(cfg["multi_repo_sources"]) == 2
        assert cfg["multi_repo_sources"][0]["app_label"] == "Frontend"
        assert cfg["multi_repo_sources"][1]["app_label"] == "Backend"
        assert cfg["audience"] == "summary"

    def test_to_generation_config_mixed_sources(self):
        """Multi-repo with both GitHub and GitLab repos."""
        ws = WizardState()
        repo1 = WizardRepository(
            source_type="github",
            url="https://github.com/a/b",
            owner="a",
            repo="b",
            token="ghp_1",
            app_label="Frontend",
        )
        repo2 = WizardRepository(
            source_type="gitlab",
            url="https://gitlab.example.com/g/p",
            project_path="g/p",
            token="glpat_abc",
            app_label="Backend",
        )
        ws.add_repository(repo1)
        ws.add_repository(repo2)

        cfg = ws.to_generation_config()
        assert len(cfg["multi_repo_sources"]) == 2
        assert cfg["github_token"] == "ghp_1"
        assert cfg["gitlab_token"] == "glpat_abc"
        assert cfg["gitlab_url"] == "https://gitlab.example.com"

    def test_reset(self):
        ws = WizardState()
        ws.source_type = "remote"
        ws.audience = "executive"
        repo = WizardRepository(source_type="github", url="https://github.com/a/b")
        ws.add_repository(repo)
        old_session = ws.session_id

        ws.reset()
        assert ws.session_id != old_session
        assert ws.source_type == ""
        assert ws.repositories == []
        assert ws.step == WizardStep.SOURCE_TYPE
        assert ws.audience == "changelog"


# ── Wizard API Endpoint Tests ──────────────────────────────────────────────


@pytest.fixture()
def wizard_client():
    """Create a test client with isolated config."""
    app = create_app({"repo_path": ".", "app_name": "Test"})
    return TestClient(app)


class TestWizardGetState:
    """GET /api/wizard/state"""

    def test_initial_state(self, wizard_client):
        r = wizard_client.get("/api/wizard/state")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["step"] == "source_type"
        assert data["repository_count"] == 0

    def test_state_contains_all_fields(self, wizard_client):
        r = wizard_client.get("/api/wizard/state")
        data = r.json()
        assert "session_id" in data
        assert "source_type" in data
        assert "repositories" in data
        assert "release_range" in data
        assert "options" in data


class TestWizardReset:
    """POST /api/wizard/reset"""

    def test_reset(self, wizard_client):
        # First add some state
        wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "remote"},
        )
        # Then reset
        r = wizard_client.post("/api/wizard/reset")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["step"] == "source_type"
        assert data["repository_count"] == 0


class TestWizardSourceType:
    """PUT /api/wizard/source-type"""

    def test_set_local(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "local"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["source_type"] == "local"
        assert data["step"] == "repositories"

    def test_set_remote(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "remote"},
        )
        assert r.status_code == 200
        assert r.json()["source_type"] == "remote"

    def test_invalid_source_type(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "invalid"},
        )
        assert r.status_code == 400


class TestWizardAddRepository:
    """POST /api/wizard/repositories"""

    def test_add_github_repo(self, wizard_client):
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "https://github.com/polprog-tech/ReleasePilot",
                "token": "ghp_test",
                "app_label": "ReleasePilot",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["repository"]["source_type"] == "github"
        assert data["repository"]["app_label"] == "ReleasePilot"
        assert data["repository"]["token_set"] is True
        assert data["repository_count"] == 1

    def test_add_gitlab_repo(self, wizard_client):
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "gitlab",
                "url": "https://gitlab.example.com/group/project",
                "token": "glpat_test",
                "app_label": "Backend",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["repository"]["source_type"] == "gitlab"

    def test_add_local_repo(self, wizard_client, tmp_path):
        (tmp_path / ".git").mkdir()
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "local",
                "path": str(tmp_path),
                "app_label": "LocalApp",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["repository"]["source_type"] == "local"
        assert data["repository"]["app_label"] == "LocalApp"

    def test_add_missing_url(self, wizard_client):
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={"source_type": "github"},
        )
        assert r.status_code == 400

    def test_add_invalid_url(self, wizard_client):
        r = wizard_client.post(
            "/api/wizard/repositories",
            json={
                "source_type": "github",
                "url": "not-a-valid-url",
            },
        )
        assert r.status_code == 400

    def test_add_duplicate(self, wizard_client):
        """Adding the same repo twice should fail."""
        payload = {
            "source_type": "github",
            "url": "https://github.com/polprog-tech/ReleasePilot",
            "token": "ghp_test",
        }
        wizard_client.post("/api/wizard/repositories", json=payload)
        r = wizard_client.post("/api/wizard/repositories", json=payload)
        assert r.status_code == 400
        assert "already" in r.json()["error"].lower()

    def test_add_multiple_repos(self, wizard_client):
        """Multiple different repos should succeed."""
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
        assert r.status_code == 200
        assert r.json()["repository_count"] == 2


class TestWizardRemoveRepository:
    """DELETE /api/wizard/repositories/{repo_id}"""

    def test_remove_repo(self, wizard_client):
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
        assert r2.status_code == 200
        assert r2.json()["repository_count"] == 0

    def test_remove_nonexistent(self, wizard_client):
        r = wizard_client.delete("/api/wizard/repositories/nonexistent")
        assert r.status_code == 404


class TestWizardListRepositories:
    """GET /api/wizard/repositories"""

    def test_empty_list(self, wizard_client):
        r = wizard_client.get("/api/wizard/repositories")
        assert r.status_code == 200
        assert r.json()["repository_count"] == 0
        assert r.json()["repositories"] == []

    def test_list_after_add(self, wizard_client):
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
        assert r.status_code == 200
        data = r.json()
        assert data["repository_count"] == 1
        assert data["repositories"][0]["app_label"] == "TestApp"


class TestWizardReleaseRange:
    """PUT /api/wizard/release-range"""

    def test_set_range(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={
                "from_ref": "v1.0.0",
                "to_ref": "v2.0.0",
                "branch": "main",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["release_range"]["from_ref"] == "v1.0.0"
        assert data["release_range"]["to_ref"] == "v2.0.0"
        assert data["release_range"]["branch"] == "main"
        assert data["step"] == "audience"

    def test_set_date_range(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "2025-01-01"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["release_range"]["since_date"] == "2025-01-01"

    def test_invalid_date(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "not-a-date"},
        )
        assert r.status_code == 400

    def test_valid_date_format(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/release-range",
            json={"since_date": "2025-12-31"},
        )
        assert r.status_code == 200


class TestWizardOptions:
    """PUT /api/wizard/options"""

    def test_set_options(self, wizard_client):
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

    def test_invalid_audience(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/options",
            json={"audience": "invalid"},
        )
        assert r.status_code == 400

    def test_invalid_format(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/options",
            json={"output_format": "invalid"},
        )
        assert r.status_code == 400

    def test_invalid_language(self, wizard_client):
        r = wizard_client.put(
            "/api/wizard/options",
            json={"language": "xx"},
        )
        assert r.status_code == 400

    def test_partial_update(self, wizard_client):
        """Only updating some fields should work."""
        r = wizard_client.put(
            "/api/wizard/options",
            json={"audience": "summary"},
        )
        assert r.status_code == 200
        assert r.json()["options"]["audience"] == "summary"
        # Defaults preserved
        assert r.json()["options"]["output_format"] == "markdown"


class TestWizardValidateUrl:
    """POST /api/wizard/validate-url"""

    def test_validate_github(self, wizard_client):
        r = wizard_client.post(
            "/api/wizard/validate-url",
            json={"url": "https://github.com/owner/repo"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["provider"] == "github"
        assert data["owner"] == "owner"
        assert data["repo"] == "repo"

    def test_validate_gitlab(self, wizard_client):
        r = wizard_client.post(
            "/api/wizard/validate-url",
            json={"url": "https://gitlab.example.com/group/project"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["provider"] == "gitlab"

    def test_validate_invalid(self, wizard_client):
        r = wizard_client.post(
            "/api/wizard/validate-url",
            json={"url": "https://bitbucket.org/owner/repo"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False

    def test_validate_missing_url(self, wizard_client):
        r = wizard_client.post(
            "/api/wizard/validate-url",
            json={},
        )
        assert r.status_code == 400


class TestWizardGenerate:
    """POST /api/wizard/generate"""

    def test_generate_no_repos(self, wizard_client):
        r = wizard_client.post("/api/wizard/generate")
        assert r.status_code == 400
        assert "no repositories" in r.json()["error"].lower()

    def test_generate_starts_generation(self, wizard_client):
        """After adding a repo and configuring, generation should start."""
        # Add a local repo
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
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["message"] == "Generation started"
        assert data["repository_count"] == 1


class TestWizardFullFlow:
    """Integration tests for the complete wizard flow."""

    def test_full_flow_single_remote(self, wizard_client):
        """Complete wizard flow: source type → add repo → range → options → state check."""
        # Step 1: Source type
        r = wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "remote"},
        )
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

    def test_full_flow_multi_repo(self, wizard_client):
        """Multi-repo wizard flow with two GitHub repositories."""
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

    def test_flow_reset_and_restart(self, wizard_client):
        """Wizard reset should clear all state."""
        # Build some state
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
        assert r.json()["step"] == "source_type"
        assert r.json()["repository_count"] == 0

        # Verify repos are gone
        r = wizard_client.get("/api/wizard/repositories")
        assert r.json()["repository_count"] == 0

    def test_remove_and_re_add(self, wizard_client):
        """Remove a repo and add a different one."""
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
        assert r2.json()["repository_count"] == 1
        assert r2.json()["repository"]["owner"] == "org"
        assert r2.json()["repository"]["repo"] == "new-repo"


# ── Settings Builder Tests ──────────────────────────────────────────────────


class TestBuildSettingsMultiRepo:
    """Test _build_settings_from_config with multi_repo_sources."""

    def test_multi_repo_sources_passthrough(self):
        """Multi-repo sources should be passed through to Settings."""
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
        assert settings.is_multi_repo is True
        assert len(settings.multi_repo_sources) == 2
        assert settings.multi_repo_sources[0]["app_label"] == "Frontend"
        assert settings.multi_repo_sources[1]["app_label"] == "Backend"

    def test_empty_multi_repo_sources(self):
        """Empty multi_repo_sources should not activate multi-repo mode."""
        from releasepilot.web.server import _build_settings_from_config

        config = {"since_date": "2025-01-01", "multi_repo_sources": []}
        settings = _build_settings_from_config(config)
        assert settings.is_multi_repo is False

    def test_single_github_source(self):
        """Single GitHub source should not use multi-repo mode."""
        from releasepilot.web.server import _build_settings_from_config

        config = {
            "since_date": "2025-01-01",
            "github_owner": "org",
            "github_repo": "project",
            "github_token": "ghp_test",
        }
        settings = _build_settings_from_config(config)
        assert settings.is_github_source is True
        assert settings.is_multi_repo is False


# ── App State Integration Tests ─────────────────────────────────────────────


class TestAppStateWizard:
    """Test AppState has wizard integration."""

    def test_appstate_has_wizard(self):
        state = AppState()
        assert hasattr(state, "wizard")
        assert isinstance(state.wizard, WizardState)

    def test_wizard_is_independent(self):
        """Each AppState gets its own wizard."""
        s1 = AppState()
        s2 = AppState()
        assert s1.wizard.session_id != s2.wizard.session_id


# ── Directory Scan Endpoint Tests ──────────────────────────────────────────


class TestScanDirectory:
    """POST /api/scan-directory"""

    def test_missing_path(self, wizard_client):
        r = wizard_client.post("/api/scan-directory", json={})
        assert r.status_code == 400
        data = r.json()
        assert data["ok"] is False
        assert "path" in data["error"].lower()

    def test_empty_path(self, wizard_client):
        r = wizard_client.post("/api/scan-directory", json={"path": ""})
        assert r.status_code == 400

    def test_unsafe_path_rejected(self, wizard_client):
        r = wizard_client.post("/api/scan-directory", json={"path": "/tmp;rm -rf"})
        assert r.status_code == 400
        data = r.json()
        assert data["ok"] is False
        assert "unsafe" in data["error"].lower()

    def test_nonexistent_path(self, wizard_client):
        r = wizard_client.post(
            "/api/scan-directory",
            json={"path": "/nonexistent/path/that/does/not/exist"},
        )
        assert r.status_code == 400

    def test_scan_current_directory(self, wizard_client):
        """Current directory (ReleasePilot repo root) should be found as a git repo."""
        r = wizard_client.post("/api/scan-directory", json={"path": "."})
        data = r.json()
        assert data["ok"] is True
        assert data["count"] >= 1
        assert len(data["repos"]) >= 1
        # Current dir itself should be in the results
        names = [repo["name"] for repo in data["repos"]]
        assert any(name for name in names)

    def test_scan_returns_repo_structure(self, wizard_client):
        r = wizard_client.post("/api/scan-directory", json={"path": "."})
        data = r.json()
        assert data["ok"] is True
        for repo in data["repos"]:
            assert "name" in repo
            assert "path" in repo
            assert repo["name"]  # non-empty
            assert repo["path"]  # non-empty

    def test_scan_no_repos_in_dir(self, wizard_client, tmp_path):
        """An empty directory should return 404 with no repos."""
        r = wizard_client.post("/api/scan-directory", json={"path": str(tmp_path)})
        assert r.status_code == 404
        data = r.json()
        assert data["ok"] is False
        assert "no git" in data["error"].lower()

    def test_scan_finds_nested_repos(self, wizard_client, tmp_path):
        """Create fake repos in a parent dir and verify scanning."""
        # Create two fake git repos
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
        assert data["ok"] is True
        assert data["count"] == 2
        names = sorted(repo["name"] for repo in data["repos"])
        assert names == ["alpha", "beta"]
