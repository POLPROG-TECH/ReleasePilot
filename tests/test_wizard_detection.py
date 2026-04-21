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
    WizardRepository,
)

# ── Wizard API Endpoint Tests ──────────────────────────────────────────────


@pytest.fixture()
def wizard_client():
    """Create a test client with isolated config."""
    app = create_app({"repo_path": ".", "app_name": "Test"})
    return TestClient(app)


class TestDetectProvider:
    """Tests for detect_provider()."""

    """GIVEN a scenario for github url"""

    def test_github_url(self):
        """WHEN the test exercises github url"""
        """THEN the expected behavior for github url is observed"""
        assert detect_provider("https://github.com/owner/repo") == "github"

    """GIVEN a scenario for github with www"""

    def test_github_with_www(self):
        """WHEN the test exercises github with www"""
        """THEN the expected behavior for github with www is observed"""
        assert detect_provider("https://www.github.com/owner/repo") == "github"

    """GIVEN a scenario for gitlab url"""

    def test_gitlab_url(self):
        """WHEN the test exercises gitlab url"""
        """THEN the expected behavior for gitlab url is observed"""
        assert detect_provider("https://gitlab.com/group/project") == "gitlab"

    """GIVEN a scenario for self hosted gitlab"""

    def test_self_hosted_gitlab(self):
        """WHEN the test exercises self hosted gitlab"""
        """THEN the expected behavior for self hosted gitlab is observed"""
        assert detect_provider("https://gitlab.example.com/g/p") == "gitlab"

    """GIVEN a scenario for unknown url"""

    def test_unknown_url(self):
        """WHEN the test exercises unknown url"""
        """THEN the expected behavior for unknown url is observed"""
        assert detect_provider("https://bitbucket.org/owner/repo") == "unknown"

    """GIVEN a scenario for case insensitive"""

    def test_case_insensitive(self):
        """WHEN the test exercises case insensitive"""
        """THEN the expected behavior for case insensitive is observed"""
        assert detect_provider("https://GITHUB.COM/owner/repo") == "github"


class TestValidateRepoSource:
    """Tests for validate_repo_source()."""

    """GIVEN a scenario for empty input"""

    def test_empty_input(self):
        """WHEN the test exercises empty input"""
        result = validate_repo_source("")
        """THEN the expected behavior for empty input is observed"""
        assert not result.valid
        assert "required" in result.error.lower()

    """GIVEN a scenario for whitespace only"""

    def test_whitespace_only(self):
        """WHEN the test exercises whitespace only"""
        result = validate_repo_source("   ")
        """THEN the expected behavior for whitespace only is observed"""
        assert not result.valid

    """GIVEN a scenario for github valid url"""

    def test_github_valid_url(self):
        """WHEN the test exercises github valid url"""
        result = validate_repo_source("https://github.com/polprog-tech/ReleasePilot")
        """THEN the expected behavior for github valid url is observed"""
        assert result.valid
        assert result.provider == "github"
        assert result.owner == "polprog-tech"
        assert result.repo == "ReleasePilot"
        assert result.display_name == "polprog-tech/ReleasePilot"

    """GIVEN a scenario for github with git suffix"""

    def test_github_with_git_suffix(self):
        """WHEN the test exercises github with git suffix"""
        result = validate_repo_source("https://github.com/owner/repo.git")
        """THEN the expected behavior for github with git suffix is observed"""
        assert result.valid
        assert result.provider == "github"
        assert result.repo == "repo"

    """GIVEN a scenario for github with trailing slash"""

    def test_github_with_trailing_slash(self):
        """WHEN the test exercises github with trailing slash"""
        result = validate_repo_source("https://github.com/owner/repo/")
        """THEN the expected behavior for github with trailing slash is observed"""
        assert result.valid
        assert result.provider == "github"

    """GIVEN Single-segment GitHub URL is now detected as org/user page"""

    def test_github_invalid_format(self):
        """WHEN the test exercises github invalid format"""
        result = validate_repo_source("https://github.com/onlyowner")
        """THEN the expected behavior for github invalid format is observed"""
        assert result.valid
        assert result.provider == "github"
        assert result.is_org is True
        assert result.org_name == "onlyowner"

    """GIVEN When no token is provided and no env var, requires_token should be True"""

    def test_github_token_required(self):
        """WHEN the test exercises github token required"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RELEASEPILOT_GITHUB_TOKEN", None)
            result = validate_repo_source(
                "https://github.com/owner/repo",
                token="",
            )
            assert result.valid
            assert result.requires_token is True

    """GIVEN a scenario for github token provided"""

    def test_github_token_provided(self):
        """WHEN the test exercises github token provided"""
        result = validate_repo_source(
            "https://github.com/owner/repo",
            token="ghp_test123",
        )
        """THEN the expected behavior for github token provided is observed"""
        assert result.valid
        assert result.requires_token is False

    """GIVEN a scenario for gitlab valid url"""

    def test_gitlab_valid_url(self):
        """WHEN the test exercises gitlab valid url"""
        result = validate_repo_source("https://gitlab.example.com/group/project")
        """THEN the expected behavior for gitlab valid url is observed"""
        assert result.valid
        assert result.provider == "gitlab"
        assert result.project_path == "group/project"
        assert result.owner == "group"
        assert result.repo == "project"

    """GIVEN a scenario for gitlab nested groups"""

    def test_gitlab_nested_groups(self):
        """WHEN the test exercises gitlab nested groups"""
        result = validate_repo_source("https://gitlab.example.com/org/team/sub/project")
        """THEN the expected behavior for gitlab nested groups is observed"""
        assert result.valid
        assert result.project_path == "org/team/sub/project"
        assert result.owner == "org/team/sub"
        assert result.repo == "project"

    """GIVEN a scenario for gitlab with git suffix"""

    def test_gitlab_with_git_suffix(self):
        """WHEN the test exercises gitlab with git suffix"""
        result = validate_repo_source("https://gitlab.example.com/group/project.git")
        """THEN the expected behavior for gitlab with git suffix is observed"""
        assert result.valid
        assert result.project_path == "group/project"

    """GIVEN a scenario for gitlab no path"""

    def test_gitlab_no_path(self):
        """WHEN the test exercises gitlab no path"""
        result = validate_repo_source("https://gitlab.example.com/")
        """THEN the expected behavior for gitlab no path is observed"""
        assert not result.valid
        assert result.provider == "gitlab"

    """GIVEN a scenario for local path nonexistent"""

    def test_local_path_nonexistent(self):
        """WHEN the test exercises local path nonexistent"""
        result = validate_repo_source("/tmp/nonexistent-repo-12345")
        """THEN the expected behavior for local path nonexistent is observed"""
        assert not result.valid
        assert result.provider == "local"
        assert "not exist" in result.error.lower() or "does not exist" in result.error.lower()

    """GIVEN A real directory but not a git repo"""

    def test_local_path_not_git(self, tmp_path):
        """WHEN the test exercises local path not git"""
        result = validate_repo_source(str(tmp_path))
        """THEN the expected behavior for local path not git is observed"""
        assert not result.valid
        assert "git" in result.error.lower()

    """GIVEN A real directory with .git subdirectory"""

    def test_local_path_is_git(self, tmp_path):
        """WHEN the test exercises local path is git"""
        (tmp_path / ".git").mkdir()
        result = validate_repo_source(str(tmp_path))
        """THEN the expected behavior for local path is git is observed"""
        assert result.valid
        assert result.provider == "local"
        assert result.source_type == "local"

    """GIVEN a scenario for unknown provider"""

    def test_unknown_provider(self):
        """WHEN the test exercises unknown provider"""
        result = validate_repo_source("https://bitbucket.org/owner/repo")
        """THEN the expected behavior for unknown provider is observed"""
        assert not result.valid
        assert result.provider == "unknown"

    """GIVEN a scenario for custom app label"""

    def test_custom_app_label(self):
        """WHEN the test exercises custom app label"""
        result = validate_repo_source(
            "https://github.com/owner/repo",
            app_label="MyApp",
        )
        """THEN the expected behavior for custom app label is observed"""
        assert result.valid
        assert result.display_name == "MyApp"

    """GIVEN a scenario for explicit provider override"""

    def test_explicit_provider_override(self):
        """WHEN the test exercises explicit provider override"""
        result = validate_repo_source(
            "https://custom-gitlab.internal/group/project",
            provider="gitlab",
        )
        """THEN the expected behavior for explicit provider override is observed"""
        assert result.valid
        assert result.provider == "gitlab"


class TestWizardRepository:
    """Tests for WizardRepository dataclass."""

    """GIVEN a scenario for display name github"""

    def test_display_name_github(self):
        """WHEN the test exercises display name github"""
        repo = WizardRepository(source_type="github", owner="org", repo="project")
        """THEN the expected behavior for display name github is observed"""
        assert repo.display_name == "org/project"

    """GIVEN a scenario for display name gitlab"""

    def test_display_name_gitlab(self):
        """WHEN the test exercises display name gitlab"""
        repo = WizardRepository(source_type="gitlab", project_path="group/sub/proj")
        """THEN the expected behavior for display name gitlab is observed"""
        assert repo.display_name == "group/sub/proj"

    """GIVEN a scenario for display name custom label"""

    def test_display_name_custom_label(self):
        """WHEN the test exercises display name custom label"""
        repo = WizardRepository(source_type="github", owner="org", repo="proj", app_label="MyApp")
        """THEN the expected behavior for display name custom label is observed"""
        assert repo.display_name == "MyApp"

    """GIVEN a scenario for display name local"""

    def test_display_name_local(self):
        """WHEN the test exercises display name local"""
        repo = WizardRepository(source_type="local", url="/path/to/repo")
        """THEN the expected behavior for display name local is observed"""
        assert repo.display_name == "/path/to/repo"

    """GIVEN a scenario for requires token github no token"""

    def test_requires_token_github_no_token(self):
        """WHEN the test exercises requires token github no token"""
        repo = WizardRepository(source_type="github", owner="o", repo="r")
        """THEN the expected behavior for requires token github no token is observed"""
        assert repo.requires_token is True

    """GIVEN a scenario for requires token github with token"""

    def test_requires_token_github_with_token(self):
        """WHEN the test exercises requires token github with token"""
        repo = WizardRepository(source_type="github", owner="o", repo="r", token="ghp_test")
        """THEN the expected behavior for requires token github with token is observed"""
        assert repo.requires_token is False

    """GIVEN a scenario for requires token local"""

    def test_requires_token_local(self):
        """WHEN the test exercises requires token local"""
        repo = WizardRepository(source_type="local", url="/path")
        """THEN the expected behavior for requires token local is observed"""
        assert repo.requires_token is False

    """GIVEN a scenario for to dict masks token"""

    def test_to_dict_masks_token(self):
        """WHEN the test exercises to dict masks token"""
        repo = WizardRepository(
            source_type="github",
            owner="org",
            repo="proj",
            token="secret_token_value",
        )
        d = repo.to_dict()
        """THEN the expected behavior for to dict masks token is observed"""
        assert "token" not in d
        assert d["token_set"] is True

    """GIVEN a scenario for to dict no token"""

    def test_to_dict_no_token(self):
        """WHEN the test exercises to dict no token"""
        repo = WizardRepository(source_type="local", url="/path")
        d = repo.to_dict()
        """THEN the expected behavior for to dict no token is observed"""
        assert d["token_set"] is False

    """GIVEN a scenario for to source dict local"""

    def test_to_source_dict_local(self):
        """WHEN the test exercises to source dict local"""
        repo = WizardRepository(source_type="local", url="/path/to/repo", app_label="MyApp")
        sd = repo.to_source_dict()
        """THEN the expected behavior for to source dict local is observed"""
        assert sd["path"] == "/path/to/repo"
        assert sd["provider"] == "local"
        assert sd["app_label"] == "MyApp"

    """GIVEN a scenario for to source dict github"""

    def test_to_source_dict_github(self):
        """WHEN the test exercises to source dict github"""
        repo = WizardRepository(
            source_type="github",
            url="https://github.com/a/b",
            owner="a",
            repo="b",
            token="ghp_123",
            app_label="Frontend",
        )
        sd = repo.to_source_dict()
        """THEN the expected behavior for to source dict github is observed"""
        assert sd["url"] == "https://github.com/a/b"
        assert sd["provider"] == "github"
        assert sd["token"] == "ghp_123"
        assert sd["app_label"] == "Frontend"

    """GIVEN a scenario for to source dict gitlab"""

    def test_to_source_dict_gitlab(self):
        """WHEN the test exercises to source dict gitlab"""
        repo = WizardRepository(
            source_type="gitlab",
            url="https://gitlab.example.com/g/p",
            project_path="g/p",
            token="glpat_abc",
            app_label="Backend",
        )
        sd = repo.to_source_dict()
        """THEN the expected behavior for to source dict gitlab is observed"""
        assert sd["url"] == "https://gitlab.example.com/g/p"
        assert sd["provider"] == "gitlab"
        assert sd["token"] == "glpat_abc"
