"""Tests for JSON configuration loading, JSON schema validation, first-commit detection, and enriched pipeline metadata."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

# ── First-commit detection ──────────────────────────────────────────────────


class TestFirstCommitDate:
    """Scenarios for first_commit_date with --all flag and branch kwarg."""

    def test_first_commit_uses_rev_list(self, tmp_path: Path) -> None:
        """GIVEN a GitSourceCollector with mocked _run_git."""
        from releasepilot.sources.git import GitSourceCollector

        git = GitSourceCollector(str(tmp_path))
        with patch.object(
            git, "_run_git", return_value="commit abc123\n2025-01-15T10:00:00+00:00"
        ) as mock:
            """WHEN first_commit_date is called without branch kwarg."""
            result = git.first_commit_date()
            args = mock.call_args[0][0]

            """THEN rev-list --max-parents=0 is used with HEAD."""
            assert "rev-list" in args
            assert "--max-parents=0" in args
            assert "HEAD" in args
            assert result == "2025-01-15T10:00:00+00:00"

    def test_first_commit_with_branch(self, tmp_path: Path) -> None:
        """GIVEN a GitSourceCollector with mocked _run_git."""
        from releasepilot.sources.git import GitSourceCollector

        git = GitSourceCollector(str(tmp_path))
        with patch.object(
            git, "_run_git", return_value="commit abc123\n2025-02-01T08:00:00+00:00"
        ) as mock:
            """WHEN first_commit_date is called with branch='develop'."""
            result = git.first_commit_date(branch="develop")
            args = mock.call_args[0][0]

            """THEN the branch name appears and HEAD is absent."""
            assert "develop" in args
            assert "HEAD" not in args
            assert result == "2025-02-01T08:00:00+00:00"

    def test_first_commit_empty_repo(self, tmp_path: Path) -> None:
        """GIVEN a GitSourceCollector where _run_git raises GitCollectionError."""
        from releasepilot.sources.git import GitCollectionError, GitSourceCollector

        git = GitSourceCollector(str(tmp_path))
        with patch.object(git, "_run_git", side_effect=GitCollectionError("no commits")):
            """WHEN first_commit_date is called THEN None is returned."""
            assert git.first_commit_date() is None

    def test_first_commit_in_real_git_repo(self, tmp_path: Path) -> None:
        """GIVEN a real git repo with multiple branches and dated commits."""
        from releasepilot.sources.git import GitSourceCollector

        repo = tmp_path / "repo"
        repo.mkdir()
        env = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2025-01-10T10:00:00+00:00",
            "GIT_COMMITTER_DATE": "2025-01-10T10:00:00+00:00",
        }
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "t@t.com"], capture_output=True
        )
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], capture_output=True)

        # First commit on main
        (repo / "f1.txt").write_text("a")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "first"], capture_output=True, env=env
        )

        # Create a feature branch with a newer commit
        subprocess.run(["git", "-C", str(repo), "checkout", "-b", "feature"], capture_output=True)
        env2 = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2025-03-01T10:00:00+00:00",
            "GIT_COMMITTER_DATE": "2025-03-01T10:00:00+00:00",
        }
        (repo / "f2.txt").write_text("b")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "feature commit"],
            capture_output=True,
            env=env2,
        )

        git = GitSourceCollector(str(repo))

        """WHEN first_commit_date is called with and without branch."""
        # --all should find the oldest commit (2025-01-10)
        first_all = git.first_commit_date()

        """THEN the oldest commit date is returned."""
        assert first_all is not None
        assert first_all.startswith("2025-01-10")

        # Branch-specific: feature branch has both commits reachable
        first_feature = git.first_commit_date(branch="feature")
        assert first_feature is not None
        assert first_feature.startswith("2025-01-10")


# ── Richer PipelineStats ────────────────────────────────────────────────────


class TestPipelineStats:
    """Scenarios for extended PipelineStats with category, contributor, and scope data."""

    def test_category_counts(self) -> None:
        """GIVEN a PipelineStats instance."""
        from releasepilot.pipeline.orchestrator import PipelineStats

        stats = PipelineStats()

        """WHEN category_counts are assigned."""
        stats.category_counts = {"feat": 5, "fix": 3, "refactor": 1}

        """THEN the counts are accessible and correct."""
        assert stats.category_counts["feat"] == 5
        assert stats.category_counts["fix"] == 3

    def test_contributor_count(self) -> None:
        """GIVEN a PipelineStats instance."""
        from releasepilot.pipeline.orchestrator import PipelineStats

        stats = PipelineStats()

        """WHEN contributor_count is assigned."""
        stats.contributor_count = 7

        """THEN the count is correct."""
        assert stats.contributor_count == 7

    def test_scopes(self) -> None:
        """GIVEN a PipelineStats instance."""
        from releasepilot.pipeline.orchestrator import PipelineStats

        stats = PipelineStats()

        """WHEN scopes are assigned."""
        stats.scopes = ("api", "auth", "dashboard")

        """THEN the scopes are accessible and correct."""
        assert "api" in stats.scopes
        assert len(stats.scopes) == 3

    def test_detailed_summary_full(self) -> None:
        """GIVEN a fully populated PipelineStats."""
        from releasepilot.pipeline.orchestrator import PipelineStats

        stats = PipelineStats()
        stats.raw = 20
        stats.after_filter = 15
        stats.after_dedup = 12
        stats.final = 12
        stats.contributor_count = 4
        stats.scopes = ("api", "auth", "dashboard")
        stats.category_counts = {"feat": 6, "fix": 4, "refactor": 2}

        """WHEN detailed_summary is called."""
        detail = stats.detailed_summary()

        """THEN the summary includes contributor, component, and category info."""
        assert "Contributors: 4" in detail
        assert "Components: api, auth, dashboard" in detail
        assert "feat: 6" in detail
        assert "fix: 4" in detail
        assert "refactor: 2" in detail

    def test_detailed_summary_minimal(self) -> None:
        """GIVEN a PipelineStats with only basic counts set."""
        from releasepilot.pipeline.orchestrator import PipelineStats

        stats = PipelineStats()
        stats.raw = 5
        stats.after_filter = 5
        stats.after_dedup = 5
        stats.final = 5

        """WHEN detailed_summary is called."""
        detail = stats.detailed_summary()

        """THEN the summary omits contributor, component, and category info."""
        assert "Contributors" not in detail
        assert "Components" not in detail
        assert "Categories" not in detail

    def test_process_with_stats_enriches(self) -> None:
        """GIVEN ChangeItems with authors and scopes."""
        from releasepilot.config.settings import FilterConfig, Settings
        from releasepilot.domain.enums import ChangeCategory
        from releasepilot.domain.models import ChangeItem
        from releasepilot.pipeline.orchestrator import process_with_stats

        items = [
            ChangeItem(
                id="1",
                title="add auth",
                raw_message="feat(auth): add auth",
                category=ChangeCategory.OTHER,
                authors=("alice",),
                scope="auth",
            ),
            ChangeItem(
                id="2",
                title="fix api",
                raw_message="fix(api): fix api",
                category=ChangeCategory.OTHER,
                authors=("bob",),
                scope="api",
            ),
            ChangeItem(
                id="3",
                title="docs update",
                raw_message="docs: update readme",
                category=ChangeCategory.OTHER,
                authors=("alice",),
            ),
        ]
        settings = Settings(filter=FilterConfig())

        """WHEN process_with_stats is called."""
        processed, stats = process_with_stats(settings, items)

        """THEN stats are enriched with category and contributor data."""
        assert stats.contributor_count >= 1  # At least one author found
        assert isinstance(stats.category_counts, dict)


# ── JSON config loading ─────────────────────────────────────────────────────


class TestJsonConfig:
    """Scenarios for JSON config file loading."""

    def test_load_json_config(self, tmp_path: Path) -> None:
        """GIVEN a .releasepilot.json file with valid configuration."""
        from releasepilot.config.file_config import load_config

        cfg_data = {
            "app_name": "TestApp",
            "audience": "user",
            "language": "de",
            "branch": "develop",
        }
        (tmp_path / ".releasepilot.json").write_text(json.dumps(cfg_data))

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN all values are loaded correctly."""
        assert cfg.app_name == "TestApp"
        assert cfg.audience == "user"
        assert cfg.language == "de"
        assert cfg.branch == "develop"
        assert ".releasepilot.json" in cfg.source

    def test_json_takes_precedence_over_toml(self, tmp_path: Path) -> None:
        """GIVEN both .releasepilot.json and .releasepilot.toml files exist."""
        from releasepilot.config.file_config import load_config

        # JSON config
        (tmp_path / ".releasepilot.json").write_text(json.dumps({"app_name": "FromJSON"}))
        # TOML config
        (tmp_path / ".releasepilot.toml").write_text('app_name = "FromTOML"')

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN the JSON config takes precedence."""
        assert cfg.app_name == "FromJSON"

    def test_invalid_json_falls_through(self, tmp_path: Path) -> None:
        """GIVEN an invalid .releasepilot.json and a valid .releasepilot.toml."""
        from releasepilot.config.file_config import load_config

        (tmp_path / ".releasepilot.json").write_text("not valid json {{{")
        (tmp_path / ".releasepilot.toml").write_text('app_name = "FallbackTOML"')

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN the TOML config is used as fallback."""
        # Invalid JSON should be skipped, fallback to TOML
        assert cfg.app_name == "FallbackTOML"

    def test_json_schema_field(self, tmp_path: Path) -> None:
        """GIVEN a .releasepilot.json with a $schema key."""
        from releasepilot.config.file_config import load_config

        cfg_data = {
            "$schema": "./schema/releasepilot.schema.json",
            "app_name": "WithSchema",
        }
        (tmp_path / ".releasepilot.json").write_text(json.dumps(cfg_data))

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN app_name is loaded and no $schema warning is produced."""
        assert cfg.app_name == "WithSchema"
        # $schema should not trigger unknown-key warning
        schema_warnings = [w for w in cfg.warnings if w.field == "$schema"]
        assert len(schema_warnings) == 0

    def test_json_with_invalid_values(self, tmp_path: Path) -> None:
        """GIVEN a .releasepilot.json with invalid audience and language values."""
        from releasepilot.config.file_config import load_config

        cfg_data = {"audience": "managers", "language": "xx"}
        (tmp_path / ".releasepilot.json").write_text(json.dumps(cfg_data))

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN invalid values are sanitised to empty and warnings are produced."""
        # Invalid values should be sanitised to empty
        assert cfg.audience == ""
        assert cfg.language == ""
        assert len(cfg.warnings) >= 2

    def test_user_level_config(self, tmp_path: Path) -> None:
        """GIVEN a user-level config.json at the user config directory."""
        from releasepilot.config.file_config import load_config

        user_dir = tmp_path / "user_config"
        user_dir.mkdir()
        user_json = user_dir / "config.json"
        user_json.write_text(json.dumps({"app_name": "UserDefault"}))

        with patch("releasepilot.config.file_config._USER_CONFIG_DIR", user_dir):
            # Use an empty search dir (no project-level config)
            empty_dir = tmp_path / "empty_project"
            empty_dir.mkdir()

            """WHEN load_config is called with no project-level config."""
            cfg = load_config(str(empty_dir))

            """THEN the user-level config is loaded as fallback."""
            assert cfg.app_name == "UserDefault"

    def test_empty_json_returns_empty_config(self, tmp_path: Path) -> None:
        """GIVEN a .releasepilot.json containing an empty object."""
        from releasepilot.config.file_config import load_config

        (tmp_path / ".releasepilot.json").write_text("{}")

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN the config is empty."""
        assert cfg.is_empty

    def test_json_repos_list(self, tmp_path: Path) -> None:
        """GIVEN a .releasepilot.json with a repos list."""
        from releasepilot.config.file_config import load_config

        cfg_data = {"repos": ["./repo1", "./repo2", "./repo3"]}
        (tmp_path / ".releasepilot.json").write_text(json.dumps(cfg_data))

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN the repos list is loaded correctly."""
        assert cfg.repos == ["./repo1", "./repo2", "./repo3"]

    def test_ssl_verify_defaults_true(self, tmp_path: Path) -> None:
        """GIVEN a config with no SSL verify fields."""
        from releasepilot.config.file_config import load_config

        cfg_data = {"app_name": "TestApp"}
        (tmp_path / ".releasepilot.json").write_text(json.dumps(cfg_data))
        cfg = load_config(str(tmp_path))

        assert cfg.gitlab_ssl_verify is True
        assert cfg.github_ssl_verify is True

    def test_ssl_verify_false(self, tmp_path: Path) -> None:
        """GIVEN a config with SSL verify set to false."""
        from releasepilot.config.file_config import load_config

        cfg_data = {"gitlab_ssl_verify": False, "github_ssl_verify": False}
        (tmp_path / ".releasepilot.json").write_text(json.dumps(cfg_data))
        cfg = load_config(str(tmp_path))

        assert cfg.gitlab_ssl_verify is False
        assert cfg.github_ssl_verify is False

    def test_ssl_verify_string_false(self, tmp_path: Path) -> None:
        """GIVEN a config with SSL verify as string 'false'."""
        from releasepilot.config.file_config import load_config

        cfg_data = {"gitlab_ssl_verify": "false", "github_ssl_verify": "0"}
        (tmp_path / ".releasepilot.json").write_text(json.dumps(cfg_data))
        cfg = load_config(str(tmp_path))

        assert cfg.gitlab_ssl_verify is False
        assert cfg.github_ssl_verify is False

    def test_ssl_verify_kebab_case(self, tmp_path: Path) -> None:
        """GIVEN a config with kebab-case SSL verify keys."""
        from releasepilot.config.file_config import load_config

        cfg_data = {"gitlab-ssl-verify": False, "github-ssl-verify": False}
        (tmp_path / ".releasepilot.json").write_text(json.dumps(cfg_data))
        cfg = load_config(str(tmp_path))

        assert cfg.gitlab_ssl_verify is False
        assert cfg.github_ssl_verify is False


# ── JSON Schema file exists ─────────────────────────────────────────────────


class TestJsonSchema:
    """Scenarios for JSON Schema file validity and completeness."""

    def test_schema_file_exists(self) -> None:
        """GIVEN the expected schema file path."""
        schema_path = Path(__file__).parent.parent / "schema" / "releasepilot.schema.json"

        """THEN the schema file exists."""
        assert schema_path.exists(), f"Schema file not found at {schema_path}"

    def test_schema_is_valid_json(self) -> None:
        """GIVEN the schema file."""
        schema_path = Path(__file__).parent.parent / "schema" / "releasepilot.schema.json"

        """WHEN the schema is parsed as JSON."""
        data = json.loads(schema_path.read_text())

        """THEN it has the expected top-level structure."""
        assert data.get("type") == "object"
        assert "properties" in data

    def test_schema_has_all_fields(self) -> None:
        """GIVEN the schema file parsed as JSON."""
        schema_path = Path(__file__).parent.parent / "schema" / "releasepilot.schema.json"
        data = json.loads(schema_path.read_text())

        """WHEN the properties are extracted."""
        props = data["properties"]

        """THEN all expected fields are present."""
        expected = {
            "app_name",
            "audience",
            "format",
            "language",
            "branch",
            "title",
            "version",
            "show_authors",
            "show_hashes",
            "repos",
        }
        assert expected.issubset(set(props.keys()))


# ── $schema key handling in validate_config ──────────────────────────────────


class TestSchemaKeyHandling:
    """Scenarios for $schema key being silently ignored."""

    def test_schema_key_not_warned(self) -> None:
        """GIVEN a config dict containing a $schema key."""
        from releasepilot.config.file_config import validate_config

        """WHEN validate_config is called."""
        warnings = validate_config(
            {"$schema": "./schema/releasepilot.schema.json", "app_name": "X"}
        )

        """THEN no warnings are produced for the $schema key."""
        schema_warnings = [w for w in warnings if "$schema" in w.field]
        assert len(schema_warnings) == 0


# ── compose() metadata enrichment ───────────────────────────────────────────


class TestComposeMetadata:
    """Scenarios for compose() storing richer metadata from stats."""

    def test_compose_stores_contributors(self) -> None:
        """GIVEN ChangeItems, a ReleaseRange, and a fully populated PipelineStats."""
        from releasepilot.config.settings import Settings
        from releasepilot.domain.enums import ChangeCategory
        from releasepilot.domain.models import ChangeItem, ReleaseRange
        from releasepilot.pipeline.orchestrator import PipelineStats, compose

        items = [
            ChangeItem(
                id="1",
                title="feat: add X",
                raw_message="feat: add X",
                category=ChangeCategory.FEATURE,
                authors=("alice",),
            ),
        ]
        rr = ReleaseRange(from_ref="v1.0", to_ref="HEAD")
        stats = PipelineStats()
        stats.raw = 1
        stats.after_filter = 1
        stats.after_dedup = 1
        stats.final = 1
        stats.contributor_count = 1
        stats.scopes = ("core",)
        stats.category_counts = {"feature": 1}

        """WHEN compose is called with items, range, and stats."""
        notes = compose(Settings(), items, rr, stats)

        """THEN the metadata includes contributor, component, and category info."""
        assert notes.metadata.get("contributors") == "1"
        assert "core" in notes.metadata.get("components", "")
        assert "feature: 1" in notes.metadata.get("category_breakdown", "")
