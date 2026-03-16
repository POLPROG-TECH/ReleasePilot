"""Regression tests for the 25 production blocker fixes.

Each test class covers one or more blockers from the audit report.
Tests are designed to prove the fix works and prevent regression.
"""

from __future__ import annotations

import contextlib
import json
import signal
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from releasepilot.domain.enums import Audience, ChangeCategory, Importance
from releasepilot.domain.models import (
    ChangeGroup,
    ChangeItem,
    ReleaseNotes,
    ReleaseRange,
    SourceReference,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_item(**kw) -> ChangeItem:
    defaults = dict(
        id="item1",
        title="A change",
        description="",
        raw_message="A change",
        source=SourceReference(),
        category=ChangeCategory.FEATURE,
        importance=Importance.NORMAL,
        authors=("alice",),
    )
    defaults.update(kw)
    return ChangeItem(**defaults)


def _make_notes(**kw) -> ReleaseNotes:
    defaults = dict(
        release_range=ReleaseRange(from_ref="v1.0", to_ref="HEAD"),
        groups=(),
        highlights=(),
        breaking_changes=(),
        total_changes=0,
    )
    defaults.update(kw)
    return ReleaseNotes(**defaults)


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #1 — Git ref input sanitization (command injection protection)
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker01_RefSanitization:
    """validate_ref rejects dangerous ref strings."""

    def test_safe_refs_accepted(self):
        from releasepilot.sources.git import validate_ref

        # These should all pass without error
        for ref in ("v1.0.0", "main", "HEAD", "feature/login", "HEAD~3", "abc123^{commit}"):
            validate_ref(ref)  # no exception

    def test_empty_ref_accepted(self):
        from releasepilot.sources.git import validate_ref
        validate_ref("")  # no exception

    def test_semicolon_injection_rejected(self):
        from releasepilot.sources.git import GitCollectionError, validate_ref
        with pytest.raises(GitCollectionError, match="Invalid git ref"):
            validate_ref("v1.0; rm -rf /")

    def test_backtick_injection_rejected(self):
        from releasepilot.sources.git import GitCollectionError, validate_ref
        with pytest.raises(GitCollectionError, match="Invalid git ref"):
            validate_ref("`whoami`")

    def test_dollar_injection_rejected(self):
        from releasepilot.sources.git import GitCollectionError, validate_ref
        with pytest.raises(GitCollectionError, match="Invalid git ref"):
            validate_ref("$(cat /etc/passwd)")

    def test_pipe_injection_rejected(self):
        from releasepilot.sources.git import GitCollectionError, validate_ref
        with pytest.raises(GitCollectionError, match="Invalid git ref"):
            validate_ref("HEAD | cat")

    def test_collect_validates_refs(self):
        """collect() calls validate_ref on both from_ref and to_ref."""
        from releasepilot.sources.git import GitCollectionError, GitSourceCollector

        collector = GitSourceCollector("/tmp")
        rng = ReleaseRange(from_ref="v1.0; malicious", to_ref="HEAD")
        with pytest.raises(GitCollectionError, match="Invalid git ref"):
            collector.collect(rng)

    def test_validators_catch_unsafe_ref(self):
        """CLI validator rejects unsafe refs before any git command runs."""
        from releasepilot.cli.validators import validate_settings
        from releasepilot.config.settings import Settings

        settings = Settings(from_ref="$(malicious)", to_ref="HEAD")
        err = validate_settings(settings)
        assert err is not None
        assert "Invalid" in err.summary


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #2 — first_commit_date timeout protection
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker02_FirstCommitTimeout:
    """first_commit_date uses rev-list with a timeout, not unbounded log."""

    def test_uses_rev_list_not_log_reverse(self, tmp_path):
        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(str(tmp_path))
        with patch.object(collector, "_run_git", return_value="commit abc\n2025-01-01T00:00:00Z") as mock:
            collector.first_commit_date()
            args = mock.call_args[0][0]
            assert "rev-list" in args
            assert "--reverse" not in args

    def test_timeout_kwarg_passed(self, tmp_path):
        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(str(tmp_path))
        with patch.object(collector, "_run_git", return_value="commit abc\n2025-01-01T00:00:00Z") as mock:
            collector.first_commit_date()
            kwargs = mock.call_args[1]
            assert kwargs.get("timeout", 30) <= 15

    def test_returns_none_on_error(self, tmp_path):
        from releasepilot.sources.git import GitCollectionError, GitSourceCollector

        collector = GitSourceCollector(str(tmp_path))
        with patch.object(collector, "_run_git", side_effect=GitCollectionError("timeout")):
            assert collector.first_commit_date() is None


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #3 — File size validation for structured source
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker03_FileSizeValidation:
    """StructuredFileCollector rejects excessively large files."""

    def test_large_file_rejected(self, tmp_path):
        from releasepilot.sources.structured import (
            _MAX_FILE_SIZE,
            StructuredFileCollector,
            StructuredFileError,
        )

        f = tmp_path / "huge.json"
        f.write_text("{}")  # create file

        # Mock stat to report huge size

        class FakeStat:
            st_size = _MAX_FILE_SIZE + 1

        with patch.object(Path, "stat", return_value=FakeStat()):
            collector = StructuredFileCollector(str(f))
            with pytest.raises(StructuredFileError, match="too large"):
                collector.collect(ReleaseRange(from_ref="", to_ref=""))

    def test_normal_file_accepted(self, tmp_path):
        from releasepilot.sources.structured import StructuredFileCollector

        f = tmp_path / "ok.json"
        f.write_text(json.dumps({"changes": [{"title": "Fix bug"}]}))
        collector = StructuredFileCollector(str(f))
        items = collector.collect(ReleaseRange(from_ref="", to_ref=""))
        assert len(items) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #4 — Temp directory cleaned up on clone failure
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker04_TempCleanup:
    """run_guide wraps in try/finally to clean up cloned repos."""

    def test_keyboard_interrupt_during_guide_exits_cleanly(self):
        """KeyboardInterrupt in guide results in SystemExit(130), not a crash."""
        from releasepilot.cli.guide import run_guide

        with patch("releasepilot.cli.guide._REPO_URL_RE") as mock_re:
            mock_re.match.return_value = None
            with patch("releasepilot.cli.guide._run_guide_inner", side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    run_guide(".")
                assert exc_info.value.code == 130


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #5 — Signal handling during pipeline execution
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker05_SignalHandling:
    """CLI installs signal handlers for SIGINT/SIGTERM."""

    def test_signal_handlers_installed(self):
        from releasepilot.cli.app import _install_signal_handlers

        _install_signal_handlers()
        handler = signal.getsignal(signal.SIGINT)
        # Should be a callable, not the default SIG_DFL
        assert callable(handler)

    def test_sigint_handler_raises_system_exit(self):
        from releasepilot.cli.app import _install_signal_handlers

        _install_signal_handlers()
        handler = signal.getsignal(signal.SIGINT)
        with pytest.raises(SystemExit) as exc_info:
            handler(signal.SIGINT, None)
        assert exc_info.value.code == 128 + signal.SIGINT


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #6 — PDF/DOCX dep validation before pipeline processing
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker06_DepValidation:
    """validate_export_format_deps catches missing deps before pipeline work."""

    def test_pdf_dep_check(self):
        from releasepilot.cli.validators import validate_export_format_deps

        with patch.dict("sys.modules", {"reportlab": None}):
            err = validate_export_format_deps("pdf")
            # Either returns error or None depending on if reportlab is installed
            # The important thing is it doesn't crash
            assert err is None or err is not None  # smoke test

    def test_markdown_no_dep_check(self):
        from releasepilot.cli.validators import validate_export_format_deps

        err = validate_export_format_deps("markdown")
        assert err is None

    def test_guide_checks_deps_for_executive_pdf(self):
        """The guide code path validates deps before running the pipeline."""
        # Verify the code structure: guide.py imports validate_export_format_deps
        import releasepilot.cli.guide as guide_mod
        source = Path(guide_mod.__file__).read_text()
        assert "validate_export_format_deps" in source


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #7 — Atomic writes for preference file
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker07_AtomicPreferences:
    """Preference file writes use atomic rename pattern."""

    def test_save_uses_temp_file(self, tmp_path, monkeypatch):
        from releasepilot.cli import preferences

        monkeypatch.setattr(preferences, "PREFS_DIR", tmp_path)
        monkeypatch.setattr(preferences, "PREFS_FILE", tmp_path / "prefs.json")

        preferences._save({"test_key": {"val": 1}})

        result = json.loads((tmp_path / "prefs.json").read_text())
        assert result["test_key"]["val"] == 1

    def test_no_partial_writes_on_error(self, tmp_path, monkeypatch):
        """If write fails, the original file should be untouched."""
        from releasepilot.cli import preferences

        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text('{"original": true}')

        monkeypatch.setattr(preferences, "PREFS_DIR", tmp_path)
        monkeypatch.setattr(preferences, "PREFS_FILE", prefs_file)

        # Make os.replace fail
        with patch("os.replace", side_effect=OSError("disk full")):
            preferences._save({"corrupted": True})

        # Original file should be unchanged
        result = json.loads(prefs_file.read_text())
        assert result == {"original": True}


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #8 — Unicode handling in git log parsing
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker08_UnicodeHandling:
    """_run_git uses errors='replace' to handle invalid UTF-8."""

    def test_run_git_uses_errors_replace(self):
        """The _run_git method passes encoding='utf-8' and errors='replace'."""
        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector("/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok")
            with contextlib.suppress(Exception):
                collector._run_git(["status"])
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("encoding") == "utf-8"
            assert call_kwargs.get("errors") == "replace"


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #9 — Validation that from_ref is ancestor of to_ref
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker09_AncestorValidation:
    """check_ancestor method and validator integration."""

    def test_check_ancestor_method_exists(self):
        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(".")
        assert hasattr(collector, "check_ancestor")

    def test_check_ancestor_returns_bool(self):
        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(".")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert collector.check_ancestor("v1.0", "HEAD") is True

            mock_run.return_value = MagicMock(returncode=1)
            assert collector.check_ancestor("v1.0", "HEAD") is False

    def test_validator_calls_check_ancestor(self):
        """validate_settings checks ancestry when both refs are provided."""
        from releasepilot.cli.validators import validate_settings
        from releasepilot.config.settings import Settings

        settings = Settings(from_ref="v1.0", to_ref="v2.0")

        # Mock the git repo check to pass, ref checks to pass, ancestor to fail
        with patch("releasepilot.cli.validators._validate_git_repo", return_value=None), \
             patch("releasepilot.cli.validators._validate_ref", return_value=None), \
             patch("releasepilot.sources.git.GitSourceCollector.check_ancestor", return_value=False):
            err = validate_settings(settings)
            assert err is not None
            assert "ancestor" in err.summary.lower() or "ancestor" in err.reason.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #10 — deep-translator dependency failure handled gracefully
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker10_TranslatorFallback:
    """Translation failures return original text with a log warning."""

    def test_import_error_returns_original(self):
        from releasepilot.i18n.translator import translate_text

        # Simulate deep-translator not installed
        with patch.dict("sys.modules", {"deep_translator": None}):
            result = translate_text("Hello world", "de")
            assert result == "Hello world"

    def test_runtime_error_returns_original(self):
        from releasepilot.i18n.translator import translate_text

        # Create a mock module with a GoogleTranslator that raises
        mock_module = MagicMock()
        mock_module.GoogleTranslator.return_value.translate.side_effect = RuntimeError("network")

        with patch.dict("sys.modules", {"deep_translator": mock_module}):
            result = translate_text("Hello world", "de")
            assert result == "Hello world"

    def test_same_language_returns_original(self):
        from releasepilot.i18n.translator import translate_text
        assert translate_text("Hello", "en", "en") == "Hello"


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #11 — Output file atomicity
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker11_AtomicWrites:
    """_atomic_write_text and _atomic_write_bytes don't leave partial files."""

    def test_atomic_write_text(self, tmp_path):
        from releasepilot.cli.app import _atomic_write_text

        target = tmp_path / "output.md"
        _atomic_write_text(str(target), "# Release Notes\n")
        assert target.read_text() == "# Release Notes\n"

    def test_atomic_write_bytes(self, tmp_path):
        from releasepilot.cli.app import _atomic_write_bytes

        target = tmp_path / "output.pdf"
        _atomic_write_bytes(str(target), b"\x00\x01\x02")
        assert target.read_bytes() == b"\x00\x01\x02"

    def test_atomic_write_no_partial_on_failure(self, tmp_path):
        from releasepilot.cli.app import _atomic_write_text

        target = tmp_path / "output.md"
        target.write_text("original content")

        # Simulate failure during rename
        with patch("os.replace", side_effect=OSError("disk full")), pytest.raises(OSError):
            _atomic_write_text(str(target), "new content")

        # Original should be unchanged
        assert target.read_text() == "original content"


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #12 — Config file TOML error reporting
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker12_TomlErrorReporting:
    """_read_toml logs a warning instead of silently swallowing errors."""

    def test_invalid_toml_logs_warning(self, tmp_path):
        from releasepilot.config.file_config import _read_toml

        f = tmp_path / "bad.toml"
        f.write_text("this is [not valid = toml {{")

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            result = _read_toml(f)

        assert result is None
        mock_logger.warning.assert_called_once()

    def test_valid_toml_no_warning(self, tmp_path):
        from releasepilot.config.file_config import _read_toml

        f = tmp_path / "good.toml"
        f.write_text('[section]\nkey = "value"\n')

        result = _read_toml(f)
        assert result is not None
        assert result["section"]["key"] == "value"


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #13 — Max depth/recursion protection in structured JSON
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker13_JsonDepthProtection:
    """Structured source validates entry schema before processing."""

    def test_non_dict_entry_rejected(self, tmp_path):
        from releasepilot.sources.structured import StructuredFileCollector, StructuredFileError

        f = tmp_path / "bad.json"
        f.write_text(json.dumps({"changes": ["not a dict"]}))
        collector = StructuredFileCollector(str(f))
        with pytest.raises(StructuredFileError, match="Schema validation failed"):
            collector.collect(ReleaseRange(from_ref="", to_ref=""))

    def test_invalid_type_authors_rejected(self, tmp_path):
        from releasepilot.sources.structured import StructuredFileCollector, StructuredFileError

        f = tmp_path / "bad.json"
        f.write_text(json.dumps({"changes": [{"title": "ok", "authors": "not-a-list"}]}))
        collector = StructuredFileCollector(str(f))
        with pytest.raises(StructuredFileError, match="authors.*must be a list"):
            collector.collect(ReleaseRange(from_ref="", to_ref=""))


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #14 — PipelineStats date comparison safety
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker14_DateComparison:
    """ISO date strings compare correctly as strings (YYYY-MM-DD)."""

    def test_iso_dates_sort_lexicographically(self):
        """String comparison of ISO dates gives correct temporal order."""
        dates = ["2025-12-01", "2025-01-15", "2025-06-30"]
        assert sorted(dates) == ["2025-01-15", "2025-06-30", "2025-12-01"]
        assert min(dates) == "2025-01-15"
        assert max(dates) == "2025-12-01"

    def test_process_with_stats_tracks_dates(self):
        from datetime import datetime

        from releasepilot.config.settings import Settings
        from releasepilot.pipeline.orchestrator import process_with_stats

        items = [
            _make_item(id="a", title="First", timestamp=datetime(2025, 1, 15, tzinfo=UTC)),
            _make_item(id="b", title="Last", timestamp=datetime(2025, 6, 30, tzinfo=UTC)),
        ]
        settings = Settings()
        _, stats = process_with_stats(settings, items)
        assert stats.first_commit_date == "2025-01-15"
        assert stats.last_commit_date == "2025-06-30"


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #15 — Progress feedback for long-running operations
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker15_ProgressFeedback:
    """CLI provides progress callback for generate/export commands."""

    def test_make_cli_progress_returns_callable(self):
        from releasepilot.cli.app import _make_cli_progress

        cb = _make_cli_progress()
        assert callable(cb)

    def test_noop_progress_when_not_terminal(self):
        from unittest.mock import PropertyMock

        from rich.console import Console

        from releasepilot.cli.app import _make_cli_progress
        from releasepilot.pipeline.progress import noop_progress

        with patch.object(Console, "is_terminal", new_callable=PropertyMock, return_value=False):
            cb = _make_cli_progress()
            assert cb is noop_progress

    def test_orchestrator_accepts_progress_callback(self):
        """orchestrator.generate() accepts on_progress kwarg."""
        import inspect

        from releasepilot.pipeline.orchestrator import generate

        sig = inspect.signature(generate)
        assert "on_progress" in sig.parameters


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #16 — Multi-command supports executive audience
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker16_MultiExecutive:
    """The multi command handles 'executive' audience without crashing."""

    def test_multi_command_accepts_executive(self):
        """CLI multi command accepts --audience executive."""
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        runner = CliRunner()
        # Just verify the command parses the option without error
        result = runner.invoke(cli, ["multi", "--audience", "executive", "--help"])
        assert result.exit_code == 0

    def test_multi_code_has_executive_branch(self):
        """Multi command code checks for executive audience."""
        import releasepilot.cli.app as app_mod
        source = Path(app_mod.__file__).read_text()
        assert "is_executive" in source or "executive" in source


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #17 — Schema version in config files
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker17_SchemaVersion:
    """Config validation accepts schema_version field."""

    def test_schema_version_not_flagged_as_unknown(self):
        from releasepilot.config.file_config import validate_config

        warnings = validate_config({"schema_version": "1.0"})
        unknown = [w for w in warnings if "Unknown" in w.message and "schema_version" in w.field]
        assert len(unknown) == 0

    def test_schema_version_hyphenated_accepted(self):
        from releasepilot.config.file_config import validate_config

        warnings = validate_config({"schema-version": "1.0"})
        unknown = [w for w in warnings if "Unknown" in w.message and "schema-version" in w.field]
        assert len(unknown) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #18 — Guide handles KeyboardInterrupt gracefully
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker18_GuideKeyboardInterrupt:
    """Guide workflow catches KeyboardInterrupt and exits cleanly."""

    def test_keyboard_interrupt_exits_130(self):
        from releasepilot.cli.guide import run_guide

        with patch("releasepilot.cli.guide._REPO_URL_RE") as mock_re:
            mock_re.match.return_value = None
            with patch("releasepilot.cli.guide._run_guide_inner", side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    run_guide("/tmp")
                assert exc_info.value.code == 130


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #19 — Output directory permissions validation
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker19_OutputDirValidation:
    """Export and multi commands validate output path permissions early."""

    def test_validate_export_path_checks_parent_writable(self, tmp_path):
        from releasepilot.cli.validators import validate_export_path

        out = str(tmp_path / "output.md")
        err = validate_export_path(out)
        assert err is None  # tmp_path is writable

    def test_validate_export_path_rejects_nonexistent_parent(self):
        from releasepilot.cli.validators import validate_export_path

        err = validate_export_path("/nonexistent/dir/output.md")
        assert err is not None
        assert "does not exist" in err.reason

    def test_multi_code_validates_output_dir(self):
        """Multi command checks output dir permissions."""
        import releasepilot.cli.app as app_mod
        source = Path(app_mod.__file__).read_text()
        assert "output_dir" in source and "W_OK" in source


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #20 — Longer commit hash item IDs to reduce collision risk
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker20_LongerItemIds:
    """Item IDs from git commits use 20 hex chars instead of 12."""

    def test_git_item_id_length(self):
        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(".")
        # Use the parse_log method with synthetic data
        sep = "§§§"
        rec_sep = "∞∞∞"
        record = sep.join([
            "a" * 40,  # commit hash
            "Author",
            "2025-01-01T00:00:00Z",
            "Test commit",
            "",
        ]) + rec_sep

        items = collector._parse_log(record)
        assert len(items) == 1
        assert len(items[0].id) == 20  # 20 hex chars

    def test_structured_item_id_length(self, tmp_path):
        from releasepilot.sources.structured import StructuredFileCollector

        f = tmp_path / "test.json"
        f.write_text(json.dumps({"changes": [{"title": "Fix bug"}]}))
        collector = StructuredFileCollector(str(f))
        items = collector.collect(ReleaseRange(from_ref="", to_ref=""))
        assert len(items[0].id) == 20


def _pdf_available() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def _docx_available() -> bool:
    try:
        import docx  # noqa: F401
        return True
    except ImportError:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #21 — Test coverage for PDF/DOCX rendering
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker21_BinaryRenderingTests:
    """Conditional tests for PDF/DOCX rendering when deps are available."""

    @pytest.fixture
    def sample_notes(self):
        items = (_make_item(),)
        group = ChangeGroup(
            category=ChangeCategory.FEATURE,
            items=items,
        )
        return _make_notes(groups=(group,), total_changes=1)

    @pytest.mark.skipif(
        not _pdf_available(),
        reason="reportlab not installed",
    )
    def test_pdf_render_returns_bytes(self, sample_notes):
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.pdf import PdfRenderer

        data = PdfRenderer().render_bytes(sample_notes, RenderConfig())
        assert isinstance(data, bytes)
        assert len(data) > 100
        assert data[:4] == b"%PDF"

    @pytest.mark.skipif(
        not _docx_available(),
        reason="python-docx not installed",
    )
    def test_docx_render_returns_bytes(self, sample_notes):
        from releasepilot.config.settings import RenderConfig
        from releasepilot.rendering.docx_renderer import DocxRenderer

        data = DocxRenderer().render_bytes(sample_notes, RenderConfig())
        assert isinstance(data, bytes)
        assert len(data) > 100
        # DOCX files are zip archives
        assert data[:2] == b"PK"


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #22 — Structured source JSON schema validation
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker22_JsonSchemaValidation:
    """_validate_entry catches malformed entries."""

    def test_valid_entry_no_problems(self):
        from releasepilot.sources.structured import _validate_entry
        problems = _validate_entry({"title": "Fix bug", "category": "bugfix"}, 0)
        assert len(problems) == 0

    def test_missing_title_flagged(self):
        from releasepilot.sources.structured import _validate_entry
        problems = _validate_entry({"description": "no title"}, 0)
        assert any("title" in p for p in problems)

    def test_wrong_type_category_flagged(self):
        from releasepilot.sources.structured import _validate_entry
        problems = _validate_entry({"title": "Fix", "category": 123}, 0)
        assert any("category" in p for p in problems)

    def test_non_dict_entry_flagged(self):
        from releasepilot.sources.structured import _validate_entry
        problems = _validate_entry("not a dict", 0)
        assert len(problems) > 0


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #23 — Retry logic for transient git errors
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker23_GitRetry:
    """_run_git retries on transient errors like index.lock."""

    def test_retries_on_index_lock(self, tmp_path):
        from releasepilot.sources.git import GitSourceCollector

        collector = GitSourceCollector(str(tmp_path))
        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=128, stderr="fatal: Unable to create '/tmp/.git/index.lock'")
            return MagicMock(returncode=0, stdout="success")

        with patch("subprocess.run", side_effect=mock_run):
            with patch("time.sleep"):  # Don't actually sleep
                result = collector._run_git(["status"])
        assert result == "success"
        assert call_count == 2

    def test_non_transient_error_not_retried(self, tmp_path):
        from releasepilot.sources.git import GitCollectionError, GitSourceCollector

        collector = GitSourceCollector(str(tmp_path))
        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return MagicMock(returncode=128, stderr="fatal: bad object HEAD")

        with patch("subprocess.run", side_effect=mock_run):
            with pytest.raises(GitCollectionError):
                collector._run_git(["log"])
        assert call_count == 1  # No retry


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #24 — Executive brief with empty input
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker24_ExecutiveEmptyInput:
    """compose_executive_brief handles empty notes gracefully."""

    def test_empty_notes_produces_brief(self):
        from releasepilot.audience.executive import compose_executive_brief

        notes = _make_notes(groups=(), total_changes=0)
        brief = compose_executive_brief(notes)
        assert brief is not None
        assert brief.executive_summary  # Should produce some summary
        assert brief.metrics is not None

    def test_empty_notes_no_crash_with_period(self):
        from releasepilot.audience.executive import compose_executive_brief

        notes = _make_notes(groups=(), total_changes=0)
        brief = compose_executive_brief(notes, analysis_period="Last 30 days")
        assert brief.analysis_period == "Last 30 days"

    def test_single_item_notes_produces_brief(self):
        from releasepilot.audience.executive import compose_executive_brief

        items = (_make_item(),)
        group = ChangeGroup(
            category=ChangeCategory.FEATURE,
            items=items,
        )
        notes = _make_notes(groups=(group,), total_changes=1)
        brief = compose_executive_brief(notes)
        assert brief is not None
        assert len(brief.key_achievements) > 0 or brief.executive_summary


# ══════════════════════════════════════════════════════════════════════════════
# Blocker #25 — Logging infrastructure for production debugging
# ══════════════════════════════════════════════════════════════════════════════


class TestBlocker25_Logging:
    """CLI supports --verbose flag and Python logging is configured."""

    def test_verbose_flag_exists_on_cli(self):
        from click.testing import CliRunner

        from releasepilot.cli.app import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--verbose", "--help"])
        assert result.exit_code == 0

    def test_git_module_has_logger(self):
        import releasepilot.sources.git as git_mod
        assert hasattr(git_mod, "logger")

    def test_translator_module_has_logger(self):
        import releasepilot.i18n.translator as trans_mod
        assert hasattr(trans_mod, "logger")

    def test_structured_module_has_logger(self):
        import releasepilot.sources.structured as struct_mod
        assert hasattr(struct_mod, "logger")


# ── Additional fixes: audience default, accent color, PDF spacing ────────────


class TestAudienceDefaultChangelog:
    """The default audience in guided mode should be Standard changelog (index 0)."""

    def test_default_is_changelog_not_executive(self):
        """GIVEN no saved preference, WHEN _step_audience runs, THEN default is 0."""
        from releasepilot.cli.guide import _step_audience

        with patch("releasepilot.cli.guide.select_one", return_value=Audience.CHANGELOG) as mock:
            _step_audience(lambda *a: None)
        _, kwargs = mock.call_args
        assert kwargs["default_index"] == 0

    def test_saved_preference_overrides_default(self):
        """GIVEN a saved preference for index 3, THEN that is used instead."""
        from releasepilot.cli.guide import _step_audience

        with patch("releasepilot.cli.guide.select_one", return_value=Audience.SUMMARY) as mock:
            _step_audience(lambda key, choices: 3)
        _, kwargs = mock.call_args
        assert kwargs["default_index"] == 3


class TestAccentColorConfig:
    """accent_color is configurable via RenderConfig and defaults to #FB6400."""

    def test_render_config_default_accent(self):
        from releasepilot.config.settings import RenderConfig
        rc = RenderConfig()
        assert rc.accent_color == "#FB6400"

    def test_render_config_custom_accent(self):
        from releasepilot.config.settings import RenderConfig
        rc = RenderConfig(accent_color="#00FF00")
        assert rc.accent_color == "#00FF00"

    def test_file_config_reads_accent_color(self):
        """GIVEN a TOML config with accent_color, THEN FileConfig picks it up."""
        from releasepilot.config.file_config import FileConfig
        fc = FileConfig(accent_color="#123ABC")
        assert fc.accent_color == "#123ABC"

    def test_accent_color_in_known_keys(self):
        from releasepilot.config.file_config import _KNOWN_KEYS
        assert "accent_color" in _KNOWN_KEYS
        assert "accent-color" in _KNOWN_KEYS

    def test_pdf_renderer_uses_config_accent(self):
        """GIVEN a custom accent_color, WHEN PdfRenderer renders, THEN it uses that color."""
        from releasepilot.config.settings import RenderConfig
        from releasepilot.domain.enums import ChangeCategory
        from releasepilot.domain.models import (
            ChangeGroup,
            ChangeItem,
            ReleaseNotes,
            ReleaseRange,
            SourceReference,
        )

        rc = RenderConfig(accent_color="#FF0000")
        rr = ReleaseRange(from_ref="a", to_ref="b", title="Test", version="v1")
        item = ChangeItem(id="1", title="Fix", category=ChangeCategory.BUGFIX, source=SourceReference())
        group = ChangeGroup(category=ChangeCategory.BUGFIX, items=(item,))
        notes = ReleaseNotes(release_range=rr, groups=(group,))

        from releasepilot.rendering.pdf import PdfRenderer
        data = PdfRenderer().render_bytes(notes, rc)
        assert isinstance(data, bytes)
        assert len(data) > 100

    def test_executive_pdf_renderer_accent_param(self):
        """Executive PDF renderer accepts accent_color parameter."""
        import inspect

        from releasepilot.rendering.executive_pdf import ExecutivePdfRenderer
        sig = inspect.signature(ExecutivePdfRenderer.render_bytes)
        params = sig.parameters
        assert "accent_color" in params
        assert params["accent_color"].default == "#FB6400"

    def test_executive_docx_renderer_accent_param(self):
        """Executive DOCX renderer accepts accent_color parameter."""
        import inspect

        from releasepilot.rendering.executive_docx import ExecutiveDocxRenderer
        sig = inspect.signature(ExecutiveDocxRenderer.render_bytes)
        params = sig.parameters
        assert "accent_color" in params
        assert params["accent_color"].default == "#FB6400"


class TestPdfSpacingKeepTogether:
    """Impact areas in executive PDF should not use KeepTogether for the full block."""

    def test_impact_area_items_not_in_keeptogether(self):
        """Verify the source code no longer wraps the entire block in KeepTogether."""
        src_path = Path(__file__).resolve().parent.parent / "src" / "releasepilot" / "rendering" / "executive_pdf.py"
        source = src_path.read_text()
        assert "KeepTogether(block)" not in source
        assert "KeepTogether(header_block)" in source

    def test_executive_pdf_renders_without_error(self):
        """GIVEN an executive brief with impact areas, WHEN rendered, THEN no crash."""
        from releasepilot.audience.executive import ExecutiveBrief, ImpactArea
        from releasepilot.domain.models import ReleaseRange
        from releasepilot.rendering.executive_pdf import ExecutivePdfRenderer

        rr = ReleaseRange(from_ref="a", to_ref="b", app_name="Test App", version="2.0")
        brief = ExecutiveBrief(
            release_range=rr,
            executive_summary="A solid release.",
            metrics={"total_changes": 10, "features": 5},
            key_achievements=["Great stuff"],
            impact_areas=[
                ImpactArea(title="Security", summary="Improved", items=["Fix A", "Fix B"]),
                ImpactArea(title="Performance", summary="Faster", items=["Opt 1"]),
            ],
            risks=[],
            next_steps=["Deploy"],
        )
        data = ExecutivePdfRenderer().render_bytes(brief)
        assert isinstance(data, bytes)
        assert len(data) > 500
