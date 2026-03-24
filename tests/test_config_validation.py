"""Tests for config validation warnings, field sanitisation, date-range labels, and end-to-end config loading."""

from __future__ import annotations

import textwrap
from datetime import date, timedelta

from releasepilot.config.file_config import (
    _VALID_AUDIENCES,
    _VALID_FORMATS,
    _VALID_LANGUAGES,
    ConfigWarning,
    FileConfig,
    _dict_to_config,
    validate_config,
)

# ── Config validation tests ──────────────────────────────────────────────────


class TestConfigValidation:
    """Scenarios for config validation warnings."""

    def test_valid_config_no_warnings(self):
        """GIVEN a config dict with all valid fields."""
        data = {
            "app_name": "MyApp",
            "audience": "technical",
            "format": "markdown",
            "language": "en",
        }

        """WHEN validate_config is called."""
        warnings = validate_config(data)

        """THEN no warnings are returned."""
        assert warnings == []

    def test_unknown_key_warns(self):
        """GIVEN a config dict containing an unknown key."""
        data = {"app_name": "X", "unknown_field": "bad"}

        """WHEN validate_config is called."""
        warnings = validate_config(data)

        """THEN a warning is raised for the unknown field."""
        assert any(w.field == "unknown_field" for w in warnings)

    def test_invalid_audience_warns(self):
        """GIVEN a config dict with an invalid audience value."""
        data = {"audience": "invalid_audience"}

        """WHEN validate_config is called."""
        warnings = validate_config(data)

        """THEN a warning is raised for the audience field."""
        assert any(w.field == "audience" for w in warnings)

    def test_invalid_format_warns(self):
        """GIVEN a config dict with an invalid format value."""
        data = {"format": "html"}

        """WHEN validate_config is called."""
        warnings = validate_config(data)

        """THEN a warning is raised for the format field."""
        assert any(w.field == "format" for w in warnings)

    def test_invalid_language_warns(self):
        """GIVEN a config dict with an invalid language value."""
        data = {"language": "xx"}

        """WHEN validate_config is called."""
        warnings = validate_config(data)

        """THEN a warning is raised for the language field."""
        assert any(w.field == "language" for w in warnings)

    def test_repos_not_list_warns(self):
        """GIVEN a config dict where repos is a string instead of a list."""
        data = {"repos": "not-a-list"}

        """WHEN validate_config is called."""
        warnings = validate_config(data)

        """THEN a warning is raised for the repos field."""
        assert any(w.field == "repos" for w in warnings)

    def test_bool_field_type_warns(self):
        """GIVEN a config dict where a boolean field has a string value."""
        data = {"show_authors": "yes"}

        """WHEN validate_config is called."""
        warnings = validate_config(data)

        """THEN a warning is raised for the show_authors field."""
        assert any(w.field == "show_authors" for w in warnings)

    def test_string_field_type_warns(self):
        """GIVEN a config dict where a string field has an integer value."""
        data = {"branch": 123}

        """WHEN validate_config is called."""
        warnings = validate_config(data)

        """THEN a warning is raised for the branch field."""
        assert any(w.field == "branch" for w in warnings)

    def test_all_valid_audiences_accepted(self):
        """GIVEN each valid audience value from the allowed set."""
        for aud in _VALID_AUDIENCES:
            """WHEN validate_config is called with that audience."""
            """THEN no warnings are returned."""
            assert validate_config({"audience": aud}) == []

    def test_all_valid_formats_accepted(self):
        """GIVEN each valid format value from the allowed set."""
        for fmt in _VALID_FORMATS:
            """WHEN validate_config is called with that format."""
            """THEN no warnings are returned."""
            assert validate_config({"format": fmt}) == []

    def test_all_valid_languages_accepted(self):
        """GIVEN each valid language value from the allowed set."""
        for lang in _VALID_LANGUAGES:
            """WHEN validate_config is called with that language."""
            """THEN no warnings are returned."""
            assert validate_config({"language": lang}) == []

    def test_empty_config_no_warnings(self):
        """GIVEN+WHEN validate_config is called with an empty dict."""
        """THEN no warnings are returned."""
        assert validate_config({}) == []


class TestConfigSanitisation:
    """Scenarios for config sanitisation of invalid enum values."""

    def test_invalid_audience_sanitised(self):
        """GIVEN a config dict with an invalid audience value."""
        data = {"audience": "bad_value"}

        """WHEN _dict_to_config converts it to a FileConfig."""
        cfg = _dict_to_config(data)

        """THEN the audience is sanitised to empty string with warnings."""
        assert cfg.audience == ""
        assert len(cfg.warnings) > 0

    def test_invalid_format_sanitised(self):
        """GIVEN a config dict with an invalid format value."""
        data = {"format": "html"}

        """WHEN _dict_to_config converts it to a FileConfig."""
        cfg = _dict_to_config(data)

        """THEN the format is sanitised to empty string."""
        assert cfg.format == ""

    def test_invalid_language_sanitised(self):
        """GIVEN a config dict with an invalid language value."""
        data = {"language": "zz"}

        """WHEN _dict_to_config converts it to a FileConfig."""
        cfg = _dict_to_config(data)

        """THEN the language is sanitised to empty string."""
        assert cfg.language == ""

    def test_valid_values_preserved(self):
        """GIVEN a config dict with all valid enum values."""
        data = {"audience": "executive", "format": "pdf", "language": "de"}

        """WHEN _dict_to_config converts it to a FileConfig."""
        cfg = _dict_to_config(data)

        """THEN the original values are preserved."""
        assert cfg.audience == "executive"
        assert cfg.format == "pdf"
        assert cfg.language == "de"

    def test_warnings_attached_to_config(self):
        """GIVEN a config dict with multiple invalid entries."""
        data = {"audience": "bad", "mystery_key": True}

        """WHEN _dict_to_config converts it to a FileConfig."""
        cfg = _dict_to_config(data)

        """THEN at least two warnings are attached to the config."""
        assert len(cfg.warnings) >= 2


class TestFileConfigWarningsField:
    """Scenarios for FileConfig warnings field behaviour."""

    def test_empty_config_no_warnings(self):
        """GIVEN+WHEN a default FileConfig is created."""
        cfg = FileConfig()

        """THEN the warnings list is empty."""
        assert cfg.warnings == []

    def test_config_warning_str(self):
        """GIVEN a ConfigWarning with a field and message."""
        w = ConfigWarning(field="audience", message="Invalid value")

        """WHEN the warning is converted to a string."""
        """THEN it contains both the field name and the message."""
        assert "audience" in str(w)
        assert "Invalid value" in str(w)


# ── Date-range transparency tests ────────────────────────────────────────────


class TestDateRangeLabel:
    """Scenarios for date range label construction."""

    def test_last_30_days_calculation(self):
        """GIVEN today's date and a 30-day timedelta."""

        """WHEN 30 days are subtracted and converted to ISO format."""
        result = (date.today() - timedelta(days=30)).isoformat()
        expected_approx = date.today() - timedelta(days=30)

        """THEN the ISO string matches the expected date."""
        assert result == expected_approx.isoformat()

    def test_build_release_range_date_title(self):
        """GIVEN a Settings object with since_date set to 2025-01-15."""
        from releasepilot.config.settings import Settings
        from releasepilot.pipeline.orchestrator import build_release_range

        settings = Settings(
            repo_path=".",
            since_date="2025-01-15",
            branch="main",
        )

        """WHEN build_release_range is called."""
        rr = build_release_range(settings)

        """THEN the resulting title contains the since_date."""
        assert "2025-01-15" in rr.title


# ── Config file with validation end-to-end ──────────────────────────────────


class TestConfigFileValidationE2E:
    """Scenarios for end-to-end config file loading with validation."""

    def test_load_config_with_warnings(self, tmp_path):
        """GIVEN a TOML config file with invalid audience and unknown key."""
        from releasepilot.config.file_config import load_config

        toml_content = textwrap.dedent("""\
            app_name = "TestApp"
            audience = "invalid_audience"
            mystery = "key"
        """)
        (tmp_path / ".releasepilot.toml").write_text(toml_content)

        """WHEN load_config reads the file."""
        cfg = load_config(str(tmp_path))

        """THEN app_name is loaded, audience is sanitised, and warnings are present."""
        assert cfg.app_name == "TestApp"
        assert cfg.audience == ""  # Sanitised
        assert len(cfg.warnings) >= 2

    def test_load_valid_config_no_warnings(self, tmp_path):
        """GIVEN a TOML config file with all valid values."""
        from releasepilot.config.file_config import load_config

        toml_content = textwrap.dedent("""\
            app_name = "Good"
            audience = "executive"
            language = "pl"
        """)
        (tmp_path / ".releasepilot.toml").write_text(toml_content)

        """WHEN load_config reads the file."""
        cfg = load_config(str(tmp_path))

        """THEN no warnings are present and values are preserved."""
        assert cfg.warnings == []
        assert cfg.audience == "executive"
        assert cfg.language == "pl"
