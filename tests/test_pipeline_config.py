"""Tests for pipeline statistics, TOML/pyproject config loading, repo-name detection, and multi-repo support."""

from __future__ import annotations

import textwrap

from releasepilot.config.file_config import FileConfig, _dict_to_config, load_config
from releasepilot.config.settings import Settings
from releasepilot.domain.enums import ChangeCategory, Importance
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)
from releasepilot.pipeline.orchestrator import (
    PipelineStats,
    _compose_title,
    _repo_name,
    compose,
    process,
    process_with_stats,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_settings(**overrides) -> Settings:
    defaults = {"repo_path": ".", "since_date": "2025-01-01", "branch": "main"}
    defaults.update(overrides)
    return Settings(**defaults)


def _sample_items(n: int = 5) -> list[ChangeItem]:
    items = []
    for i in range(n):
        items.append(
            ChangeItem(
                id=f"item-{i}",
                title=f"Change number {i}: implement feature {i}",
                category=ChangeCategory.FEATURE,
                importance=Importance.NORMAL,
                source=SourceReference(commit_hash=f"abc{i:04d}"),
                raw_message=f"feat: change number {i}: implement feature {i}",
            )
        )
    return items


# ── PipelineStats tests ─────────────────────────────────────────────────────


class TestPipelineStats:
    """Scenarios for PipelineStats."""

    """GIVEN a freshly created PipelineStats"""

    def test_initial_values(self):
        """WHEN the test exercises initial values"""
        stats = PipelineStats()

        """THEN all counters default to zero"""
        assert stats.raw == 0
        assert stats.after_filter == 0
        assert stats.after_dedup == 0
        assert stats.final == 0

    """GIVEN a PipelineStats with populated counters"""

    def test_computed_properties(self):
        """WHEN the test exercises computed properties"""
        stats = PipelineStats()
        stats.raw = 10
        stats.after_filter = 7
        stats.after_dedup = 5
        stats.final = 5

        """THEN computed properties reflect the correct deltas"""
        assert stats.filtered_out == 3
        assert stats.dedup_removed == 2

    """GIVEN a PipelineStats with populated counters"""

    def test_summary_string(self):
        stats = PipelineStats()
        stats.raw = 20
        stats.after_filter = 15
        stats.after_dedup = 12
        stats.final = 12

        """WHEN summary() is called"""
        s = stats.summary()

        """THEN the string contains all expected counts"""
        assert "20 collected" in s
        assert "5 filtered" in s
        assert "3 deduplicated" in s
        assert "12 final" in s


class TestProcessWithStats:
    """Scenarios for process_with_stats."""

    """GIVEN sample items and default settings"""

    def test_returns_items_and_stats(self):
        items = _sample_items(5)
        settings = _make_settings()

        """WHEN process_with_stats is called"""
        result, stats = process_with_stats(settings, items)

        """THEN it returns a PipelineStats with correct counts"""
        assert isinstance(stats, PipelineStats)
        assert stats.raw == 5
        assert stats.final == len(result)
        assert stats.after_filter >= stats.after_dedup

    """GIVEN sample items and default settings"""

    def test_stats_match_process(self):
        items = _sample_items(3)
        settings = _make_settings()

        """WHEN both process and process_with_stats are called"""
        result_plain = process(settings, items)
        result_stats, stats = process_with_stats(settings, items)

        """THEN both return the same number of items"""
        assert len(result_plain) == len(result_stats)
        assert stats.final == len(result_plain)


class TestComposeStats:
    """Scenarios for compose with pipeline stats."""

    """GIVEN processed items with pipeline stats"""

    def test_metadata_includes_stats(self):
        items = _sample_items(3)
        settings = _make_settings()
        _, stats = process_with_stats(settings, items)
        rr = ReleaseRange(from_ref="2025-01-01", to_ref="main")

        """WHEN compose is called with stats"""
        notes = compose(settings, items, rr, stats)

        """THEN metadata includes pipeline information"""
        assert "raw_count" in notes.metadata
        assert "pipeline_summary" in notes.metadata

    """GIVEN sample items and default settings"""

    def test_metadata_empty_without_stats(self):
        items = _sample_items(2)
        settings = _make_settings()
        rr = ReleaseRange(from_ref="2025-01-01", to_ref="main")

        """WHEN compose is called without stats"""
        notes = compose(settings, items, rr)

        """THEN metadata does not include pipeline_summary"""
        assert "pipeline_summary" not in notes.metadata


# ── Repo name default tests ─────────────────────────────────────────────────


class TestRepoName:
    """Scenarios for _repo_name and _compose_title."""

    """GIVEN a full directory path"""

    def test_extracts_directory_name(self):
        """THEN the last directory component is returned"""
        """WHEN _repo_name is called"""
        assert _repo_name("/home/user/projects/MyApp") == "MyApp"

    """GIVEN a path ending in .git"""

    def test_strips_git_suffix(self):
        """THEN the .git suffix is stripped"""
        """WHEN _repo_name is called"""
        assert _repo_name("/tmp/my-project.git") == "my-project"

    """GIVEN '.' as repo path"""

    def test_dot_resolves_to_cwd_name(self):
        """WHEN _repo_name is called"""
        name = _repo_name(".")

        """THEN a non-empty string is returned"""
        assert name  # Should be non-empty (cwd name)

    """GIVEN settings with a repo_path"""

    def test_compose_title_without_app_name(self):
        s = _make_settings(repo_path="/tmp/SomeProject")

        """WHEN _compose_title is called with a subtitle"""
        result = _compose_title(s, "Changes")

        """THEN it returns only the subtitle"""
        # app_name is now separate; _compose_title returns only the subtitle
        assert result == "Changes"


# ── Config file tests ────────────────────────────────────────────────────────


class TestFileConfig:
    """Scenarios for FileConfig and config loading."""

    """GIVEN a default FileConfig with no arguments"""

    def test_empty_config(self):
        """WHEN the test exercises empty config"""
        cfg = FileConfig()

        """THEN it reports as empty"""
        assert cfg.is_empty

    """GIVEN a FileConfig with app_name set"""

    def test_non_empty_config(self):
        """WHEN the test exercises non empty config"""
        cfg = FileConfig(app_name="MyApp")

        """THEN it reports as non-empty"""
        assert not cfg.is_empty

    """GIVEN a dict with config values"""

    def test_dict_to_config(self):
        data = {
            "app_name": "TestApp",
            "audience": "technical",
            "language": "de",
            "repos": ["/repo1", "/repo2"],
        }

        """WHEN _dict_to_config is called"""
        cfg = _dict_to_config(data)

        """THEN FileConfig fields match the dict"""
        assert cfg.app_name == "TestApp"
        assert cfg.audience == "technical"
        assert cfg.language == "de"
        assert cfg.repos == ["/repo1", "/repo2"]

    """GIVEN a dict with kebab-case keys"""

    def test_dict_to_config_kebab_keys(self):
        data = {"app-name": "KebabApp", "show-authors": True}

        """WHEN _dict_to_config is called"""
        cfg = _dict_to_config(data)

        """THEN kebab keys map to snake_case attributes"""
        assert cfg.app_name == "KebabApp"
        assert cfg.show_authors is True

    """GIVEN a directory with no config files"""

    def test_load_config_missing_file(self, tmp_path):
        """WHEN load_config is called"""
        cfg = load_config(str(tmp_path))

        """THEN an empty config is returned"""
        assert cfg.is_empty

    """GIVEN a directory containing .releasepilot.toml"""

    def test_load_config_toml_file(self, tmp_path):
        toml_content = textwrap.dedent("""\
            app_name = "FromToml"
            audience = "user"
            language = "fr"
        """)
        (tmp_path / ".releasepilot.toml").write_text(toml_content)

        """WHEN load_config is called"""
        cfg = load_config(str(tmp_path))

        """THEN config values match the TOML file"""
        assert cfg.app_name == "FromToml"
        assert cfg.audience == "user"
        assert cfg.language == "fr"

    """GIVEN a pyproject.toml with [tool.releasepilot] section"""

    def test_load_config_pyproject_toml(self, tmp_path):
        toml_content = textwrap.dedent("""\
            [tool.releasepilot]
            app_name = "PyprojectApp"
            branch = "develop"
        """)
        (tmp_path / "pyproject.toml").write_text(toml_content)

        """WHEN load_config is called"""
        cfg = load_config(str(tmp_path))

        """THEN config values match the TOML section"""
        assert cfg.app_name == "PyprojectApp"
        assert cfg.branch == "develop"

    """GIVEN both .releasepilot.toml and pyproject.toml exist"""

    def test_dedicated_file_takes_precedence(self, tmp_path):
        (tmp_path / ".releasepilot.toml").write_text('app_name = "Dedicated"')
        (tmp_path / "pyproject.toml").write_text('[tool.releasepilot]\napp_name = "Pyproject"')

        """WHEN load_config is called"""
        cfg = load_config(str(tmp_path))

        """THEN the dedicated file takes precedence"""
        assert cfg.app_name == "Dedicated"


# ── Multi-repo CLI tests ────────────────────────────────────────────────────


class TestMultiCommand:
    """Scenarios for multi-repo CLI command."""

    """GIVEN the CLI group"""

    def test_multi_command_exists(self):
        """WHEN its commands are inspected"""
        from releasepilot.cli.app import cli

        """THEN the 'multi' command is registered"""
        assert "multi" in [c.name for c in cli.commands.values()]

    """GIVEN a CLI runner"""

    def test_multi_requires_repos(self):
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        runner = CliRunner()

        """WHEN multi is invoked without repo arguments"""
        result = runner.invoke(cli, ["multi"])

        """THEN it exits with a non-zero code"""
        assert result.exit_code != 0


# ── Markdown pipeline stats rendering ────────────────────────────────────────


class TestMarkdownPipelineStats:
    """Scenarios for Markdown pipeline stats rendering."""

    """GIVEN release notes with pipeline_summary in metadata"""

    def test_pipeline_summary_in_footer(self):
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.markdown import MarkdownRenderer

        rr = ReleaseRange(from_ref="2025-01-01", to_ref="main", title="Test")
        item = ChangeItem(
            id="t1",
            title="Test change",
            category=ChangeCategory.FEATURE,
            source=SourceReference(commit_hash="abc123"),
        )
        notes = ReleaseNotes(
            release_range=rr,
            groups=(ChangeGroup(category=ChangeCategory.FEATURE, items=(item,)),),
            total_changes=1,
            metadata={"pipeline_summary": "5 collected → 1 filtered → 0 deduplicated → 4 final"},
        )

        """WHEN MarkdownRenderer renders the notes"""
        output = MarkdownRenderer().render(notes, RenderConfig())

        """THEN the output contains the pipeline summary"""
        assert "Pipeline:" in output
        assert "5 collected" in output

    """GIVEN release notes without pipeline_summary metadata"""

    def test_no_pipeline_summary_without_metadata(self):
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.markdown import MarkdownRenderer

        rr = ReleaseRange(from_ref="2025-01-01", to_ref="main", title="Test")
        item = ChangeItem(
            id="t1",
            title="Test change",
            category=ChangeCategory.FEATURE,
            source=SourceReference(commit_hash="abc123"),
        )
        notes = ReleaseNotes(
            release_range=rr,
            groups=(ChangeGroup(category=ChangeCategory.FEATURE, items=(item,)),),
            total_changes=1,
        )

        """WHEN MarkdownRenderer renders the notes"""
        output = MarkdownRenderer().render(notes, RenderConfig())

        """THEN the output does not contain pipeline info"""
        assert "Pipeline:" not in output
