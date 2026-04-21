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
from releasepilot.web.state import (
    AppState,
    WizardRepository,
    WizardState,
    WizardStep,
)

# ── Wizard API Endpoint Tests ──────────────────────────────────────────────


@pytest.fixture()
def wizard_client():
    """Create a test client with isolated config."""
    app = create_app({"repo_path": ".", "app_name": "Test"})
    return TestClient(app)


class TestWizardState:
    """Tests for WizardState management."""

    """GIVEN a scenario for initial state"""

    def test_initial_state(self):
        """WHEN the test exercises initial state"""
        ws = WizardState()
        """THEN the expected behavior for initial state is observed"""
        assert ws.step == WizardStep.SOURCE_TYPE
        assert ws.source_type == ""
        assert ws.repositories == []
        assert ws.to_ref == "HEAD"
        assert ws.audience == "changelog"
        assert ws.output_format == "markdown"

    """GIVEN a scenario for add repository"""

    def test_add_repository(self):
        """WHEN the test exercises add repository"""
        ws = WizardState()
        repo = WizardRepository(
            source_type="github",
            url="https://github.com/a/b",
            owner="a",
            repo="b",
        )
        err = ws.add_repository(repo)
        """THEN the expected behavior for add repository is observed"""
        assert err is None
        assert len(ws.repositories) == 1
        assert ws.repositories[0].id  # auto-assigned

    """GIVEN a scenario for add duplicate rejected"""

    def test_add_duplicate_rejected(self):
        """WHEN the test exercises add duplicate rejected"""
        ws = WizardState()
        repo1 = WizardRepository(source_type="github", url="https://github.com/a/b")
        repo2 = WizardRepository(source_type="github", url="https://github.com/a/b")
        ws.add_repository(repo1)
        err = ws.add_repository(repo2)
        """THEN the expected behavior for add duplicate rejected is observed"""
        assert err is not None
        assert "already added" in err.lower()
        assert len(ws.repositories) == 1

    """GIVEN a scenario for add max repositories"""

    def test_add_max_repositories(self):
        """WHEN the test exercises add max repositories"""
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
        """THEN the expected behavior for add max repositories is observed"""
        assert err is not None
        assert "maximum" in err.lower()

    """GIVEN a scenario for remove repository"""

    def test_remove_repository(self):
        """WHEN the test exercises remove repository"""
        ws = WizardState()
        repo = WizardRepository(
            id="test-id",
            source_type="local",
            url="/path",
        )
        ws.add_repository(repo)
        """THEN the expected behavior for remove repository is observed"""
        assert ws.remove_repository("test-id") is True
        assert len(ws.repositories) == 0

    """GIVEN a scenario for remove nonexistent"""

    def test_remove_nonexistent(self):
        """WHEN the test exercises remove nonexistent"""
        ws = WizardState()
        """THEN the expected behavior for remove nonexistent is observed"""
        assert ws.remove_repository("nonexistent") is False

    """GIVEN a scenario for get repository"""

    def test_get_repository(self):
        """WHEN the test exercises get repository"""
        ws = WizardState()
        repo = WizardRepository(id="test-id", source_type="local", url="/path")
        ws.add_repository(repo)
        found = ws.get_repository("test-id")
        """THEN the expected behavior for get repository is observed"""
        assert found is not None
        assert found.id == "test-id"

    """GIVEN a scenario for get nonexistent"""

    def test_get_nonexistent(self):
        """WHEN the test exercises get nonexistent"""
        ws = WizardState()
        """THEN the expected behavior for get nonexistent is observed"""
        assert ws.get_repository("missing") is None

    """GIVEN a scenario for to dict"""

    def test_to_dict(self):
        """WHEN the test exercises to dict"""
        ws = WizardState()
        ws.source_type = "remote"
        ws.audience = "executive"
        d = ws.to_dict()
        """THEN the expected behavior for to dict is observed"""
        assert d["source_type"] == "remote"
        assert d["options"]["audience"] == "executive"
        assert d["repository_count"] == 0
        assert "session_id" in d

    """GIVEN a scenario for to generation config single local"""

    def test_to_generation_config_single_local(self):
        """WHEN the test exercises to generation config single local"""
        ws = WizardState()
        ws.since_date = "2025-01-01"
        ws.branch = "main"
        repo = WizardRepository(source_type="local", url="/path/to/repo")
        ws.add_repository(repo)

        cfg = ws.to_generation_config()
        """THEN the expected behavior for to generation config single local is observed"""
        assert cfg["repo_path"] == "/path/to/repo"
        assert cfg["since_date"] == "2025-01-01"
        assert cfg["branch"] == "main"
        assert "multi_repo_sources" not in cfg

    """GIVEN a scenario for to generation config single github"""

    def test_to_generation_config_single_github(self):
        """WHEN the test exercises to generation config single github"""
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
        """THEN the expected behavior for to generation config single github is observed"""
        assert cfg["github_owner"] == "a"
        assert cfg["github_repo"] == "b"
        assert cfg["github_token"] == "ghp_test"
        assert "multi_repo_sources" not in cfg

    """GIVEN a scenario for to generation config single gitlab"""

    def test_to_generation_config_single_gitlab(self):
        """WHEN the test exercises to generation config single gitlab"""
        ws = WizardState()
        repo = WizardRepository(
            source_type="gitlab",
            url="https://gitlab.example.com/g/p",
            project_path="g/p",
            token="glpat_abc",
        )
        ws.add_repository(repo)

        cfg = ws.to_generation_config()
        """THEN the expected behavior for to generation config single gitlab is observed"""
        assert cfg["gitlab_project"] == "g/p"
        assert cfg["gitlab_token"] == "glpat_abc"
        assert cfg["gitlab_url"] == "https://gitlab.example.com"

    """GIVEN a scenario for to generation config multi repo"""

    def test_to_generation_config_multi_repo(self):
        """WHEN the test exercises to generation config multi repo"""
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
        """THEN the expected behavior for to generation config multi repo is observed"""
        assert "multi_repo_sources" in cfg
        assert len(cfg["multi_repo_sources"]) == 2
        assert cfg["multi_repo_sources"][0]["app_label"] == "Frontend"
        assert cfg["multi_repo_sources"][1]["app_label"] == "Backend"
        assert cfg["audience"] == "summary"

    """GIVEN Multi-repo with both GitHub and GitLab repos"""

    def test_to_generation_config_mixed_sources(self):
        """WHEN the test exercises to generation config mixed sources"""
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
        """THEN the expected behavior for to generation config mixed sources is observed"""
        assert len(cfg["multi_repo_sources"]) == 2
        assert cfg["github_token"] == "ghp_1"
        assert cfg["gitlab_token"] == "glpat_abc"
        assert cfg["gitlab_url"] == "https://gitlab.example.com"

    """GIVEN a scenario for reset"""

    def test_reset(self):
        """WHEN the test exercises reset"""
        ws = WizardState()
        ws.source_type = "remote"
        ws.audience = "executive"
        repo = WizardRepository(source_type="github", url="https://github.com/a/b")
        ws.add_repository(repo)
        old_session = ws.session_id

        ws.reset()
        """THEN the expected behavior for reset is observed"""
        assert ws.session_id != old_session
        assert ws.source_type == ""
        assert ws.repositories == []
        assert ws.step == WizardStep.SOURCE_TYPE
        assert ws.audience == "changelog"


class TestWizardGetState:
    """GET /api/wizard/state"""

    """GIVEN a scenario for initial state"""

    def test_initial_state(self, wizard_client):
        """WHEN the test exercises initial state"""
        r = wizard_client.get("/api/wizard/state")
        """THEN the expected behavior for initial state is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["step"] == "source_type"
        assert data["repository_count"] == 0

    """GIVEN a scenario for state contains all fields"""

    def test_state_contains_all_fields(self, wizard_client):
        """WHEN the test exercises state contains all fields"""
        r = wizard_client.get("/api/wizard/state")
        data = r.json()
        """THEN the expected behavior for state contains all fields is observed"""
        assert "session_id" in data
        assert "source_type" in data
        assert "repositories" in data
        assert "release_range" in data
        assert "options" in data


class TestWizardReset:
    """POST /api/wizard/reset"""

    """GIVEN a scenario for reset"""

    def test_reset(self, wizard_client):
        # First add some state
        """WHEN the test exercises reset"""
        wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "remote"},
        )
        r = wizard_client.post("/api/wizard/reset")
        """THEN the expected behavior for reset is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["step"] == "source_type"
        assert data["repository_count"] == 0


class TestWizardSourceType:
    """PUT /api/wizard/source-type"""

    """GIVEN a scenario for set local"""

    def test_set_local(self, wizard_client):
        """WHEN the test exercises set local"""
        r = wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "local"},
        )
        """THEN the expected behavior for set local is observed"""
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["source_type"] == "local"
        assert data["step"] == "repositories"

    """GIVEN a scenario for set remote"""

    def test_set_remote(self, wizard_client):
        """WHEN the test exercises set remote"""
        r = wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "remote"},
        )
        """THEN the expected behavior for set remote is observed"""
        assert r.status_code == 200
        assert r.json()["source_type"] == "remote"

    """GIVEN a scenario for invalid source type"""

    def test_invalid_source_type(self, wizard_client):
        """WHEN the test exercises invalid source type"""
        r = wizard_client.put(
            "/api/wizard/source-type",
            json={"source_type": "invalid"},
        )
        """THEN the expected behavior for invalid source type is observed"""
        assert r.status_code == 400


class TestAppStateWizard:
    """Test AppState has wizard integration."""

    """GIVEN a scenario for appstate has wizard"""

    def test_appstate_has_wizard(self):
        """WHEN the test exercises appstate has wizard"""
        state = AppState()
        """THEN the expected behavior for appstate has wizard is observed"""
        assert hasattr(state, "wizard")
        assert isinstance(state.wizard, WizardState)

    """GIVEN Each AppState gets its own wizard"""

    def test_wizard_is_independent(self):
        """WHEN the test exercises wizard is independent"""
        s1 = AppState()
        s2 = AppState()
        """THEN the expected behavior for wizard is independent is observed"""
        assert s1.wizard.session_id != s2.wizard.session_id
