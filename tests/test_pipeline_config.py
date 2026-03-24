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

    def test_initial_values(self):
        """GIVEN a freshly created PipelineStats."""
        stats = PipelineStats()

        """THEN all counters default to zero."""
        assert stats.raw == 0
        assert stats.after_filter == 0
        assert stats.after_dedup == 0
        assert stats.final == 0

    def test_computed_properties(self):
        """GIVEN a PipelineStats with populated counters."""
        stats = PipelineStats()
        stats.raw = 10
        stats.after_filter = 7
        stats.after_dedup = 5
        stats.final = 5

        """THEN computed properties reflect the correct deltas."""
        assert stats.filtered_out == 3
        assert stats.dedup_removed == 2

    def test_summary_string(self):
        """GIVEN a PipelineStats with populated counters."""
        stats = PipelineStats()
        stats.raw = 20
        stats.after_filter = 15
        stats.after_dedup = 12
        stats.final = 12

        """WHEN summary() is called."""
        s = stats.summary()

        """THEN the string contains all expected counts."""
        assert "20 collected" in s
        assert "5 filtered" in s
        assert "3 deduplicated" in s
        assert "12 final" in s


class TestProcessWithStats:
    """Scenarios for process_with_stats."""

    def test_returns_items_and_stats(self):
        """GIVEN sample items and default settings."""
        items = _sample_items(5)
        settings = _make_settings()

        """WHEN process_with_stats is called."""
        result, stats = process_with_stats(settings, items)

        """THEN it returns a PipelineStats with correct counts."""
        assert isinstance(stats, PipelineStats)
        assert stats.raw == 5
        assert stats.final == len(result)
        assert stats.after_filter >= stats.after_dedup

    def test_stats_match_process(self):
        """GIVEN sample items and default settings."""
        items = _sample_items(3)
        settings = _make_settings()

        """WHEN both process and process_with_stats are called."""
        result_plain = process(settings, items)
        result_stats, stats = process_with_stats(settings, items)

        """THEN both return the same number of items."""
        assert len(result_plain) == len(result_stats)
        assert stats.final == len(result_plain)


class TestComposeStats:
    """Scenarios for compose with pipeline stats."""

    def test_metadata_includes_stats(self):
        """GIVEN processed items with pipeline stats."""
        items = _sample_items(3)
        settings = _make_settings()
        _, stats = process_with_stats(settings, items)
        rr = ReleaseRange(from_ref="2025-01-01", to_ref="main")

        """WHEN compose is called with stats."""
        notes = compose(settings, items, rr, stats)

        """THEN metadata includes pipeline information."""
        assert "raw_count" in notes.metadata
        assert "pipeline_summary" in notes.metadata

    def test_metadata_empty_without_stats(self):
        """GIVEN sample items and default settings."""
        items = _sample_items(2)
        settings = _make_settings()
        rr = ReleaseRange(from_ref="2025-01-01", to_ref="main")

        """WHEN compose is called without stats."""
        notes = compose(settings, items, rr)

        """THEN metadata does not include pipeline_summary."""
        assert "pipeline_summary" not in notes.metadata


# ── Repo name default tests ─────────────────────────────────────────────────


class TestRepoName:
    """Scenarios for _repo_name and _compose_title."""

    def test_extracts_directory_name(self):
        """GIVEN a full directory path WHEN _repo_name is called."""

        """THEN the last directory component is returned."""
        assert _repo_name("/home/user/projects/MyApp") == "MyApp"

    def test_strips_git_suffix(self):
        """GIVEN a path ending in .git WHEN _repo_name is called."""

        """THEN the .git suffix is stripped."""
        assert _repo_name("/tmp/my-project.git") == "my-project"

    def test_dot_resolves_to_cwd_name(self):
        """GIVEN '.' as repo path WHEN _repo_name is called."""
        name = _repo_name(".")

        """THEN a non-empty string is returned."""
        assert name  # Should be non-empty (cwd name)

    def test_compose_title_without_app_name(self):
        """GIVEN settings with a repo_path."""
        s = _make_settings(repo_path="/tmp/SomeProject")

        """WHEN _compose_title is called with a subtitle."""
        result = _compose_title(s, "Changes")

        """THEN it returns only the subtitle."""
        # app_name is now separate; _compose_title returns only the subtitle
        assert result == "Changes"


# ── Config file tests ────────────────────────────────────────────────────────


class TestFileConfig:
    """Scenarios for FileConfig and config loading."""

    def test_empty_config(self):
        """GIVEN a default FileConfig with no arguments."""
        cfg = FileConfig()

        """THEN it reports as empty."""
        assert cfg.is_empty

    def test_non_empty_config(self):
        """GIVEN a FileConfig with app_name set."""
        cfg = FileConfig(app_name="MyApp")

        """THEN it reports as non-empty."""
        assert not cfg.is_empty

    def test_dict_to_config(self):
        """GIVEN a dict with config values."""
        data = {
            "app_name": "TestApp",
            "audience": "technical",
            "language": "de",
            "repos": ["/repo1", "/repo2"],
        }

        """WHEN _dict_to_config is called."""
        cfg = _dict_to_config(data)

        """THEN FileConfig fields match the dict."""
        assert cfg.app_name == "TestApp"
        assert cfg.audience == "technical"
        assert cfg.language == "de"
        assert cfg.repos == ["/repo1", "/repo2"]

    def test_dict_to_config_kebab_keys(self):
        """GIVEN a dict with kebab-case keys."""
        data = {"app-name": "KebabApp", "show-authors": True}

        """WHEN _dict_to_config is called."""
        cfg = _dict_to_config(data)

        """THEN kebab keys map to snake_case attributes."""
        assert cfg.app_name == "KebabApp"
        assert cfg.show_authors is True

    def test_load_config_missing_file(self, tmp_path):
        """GIVEN a directory with no config files WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN an empty config is returned."""
        assert cfg.is_empty

    def test_load_config_toml_file(self, tmp_path):
        """GIVEN a directory containing .releasepilot.toml."""
        toml_content = textwrap.dedent("""\
            app_name = "FromToml"
            audience = "user"
            language = "fr"
        """)
        (tmp_path / ".releasepilot.toml").write_text(toml_content)

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN config values match the TOML file."""
        assert cfg.app_name == "FromToml"
        assert cfg.audience == "user"
        assert cfg.language == "fr"

    def test_load_config_pyproject_toml(self, tmp_path):
        """GIVEN a pyproject.toml with [tool.releasepilot] section."""
        toml_content = textwrap.dedent("""\
            [tool.releasepilot]
            app_name = "PyprojectApp"
            branch = "develop"
        """)
        (tmp_path / "pyproject.toml").write_text(toml_content)

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN config values match the TOML section."""
        assert cfg.app_name == "PyprojectApp"
        assert cfg.branch == "develop"

    def test_dedicated_file_takes_precedence(self, tmp_path):
        """GIVEN both .releasepilot.toml and pyproject.toml exist."""
        (tmp_path / ".releasepilot.toml").write_text('app_name = "Dedicated"')
        (tmp_path / "pyproject.toml").write_text('[tool.releasepilot]\napp_name = "Pyproject"')

        """WHEN load_config is called."""
        cfg = load_config(str(tmp_path))

        """THEN the dedicated file takes precedence."""
        assert cfg.app_name == "Dedicated"


# ── Multi-repo CLI tests ────────────────────────────────────────────────────


class TestMultiCommand:
    """Scenarios for multi-repo CLI command."""

    def test_multi_command_exists(self):
        """GIVEN the CLI group WHEN its commands are inspected."""
        from releasepilot.cli.app import cli

        """THEN the 'multi' command is registered."""
        assert "multi" in [c.name for c in cli.commands.values()]

    def test_multi_requires_repos(self):
        """GIVEN a CLI runner."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        runner = CliRunner()

        """WHEN multi is invoked without repo arguments."""
        result = runner.invoke(cli, ["multi"])

        """THEN it exits with a non-zero code."""
        assert result.exit_code != 0


# ── Markdown pipeline stats rendering ────────────────────────────────────────


class TestMarkdownPipelineStats:
    """Scenarios for Markdown pipeline stats rendering."""

    def test_pipeline_summary_in_footer(self):
        """GIVEN release notes with pipeline_summary in metadata."""
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

        """WHEN MarkdownRenderer renders the notes."""
        output = MarkdownRenderer().render(notes, RenderConfig())

        """THEN the output contains the pipeline summary."""
        assert "Pipeline:" in output
        assert "5 collected" in output

    def test_no_pipeline_summary_without_metadata(self):
        """GIVEN release notes without pipeline_summary metadata."""
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

        """WHEN MarkdownRenderer renders the notes."""
        output = MarkdownRenderer().render(notes, RenderConfig())

        """THEN the output does not contain pipeline info."""
        assert "Pipeline:" not in output
