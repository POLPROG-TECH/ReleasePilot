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

    """GIVEN a config dict with all valid fields"""

    def test_valid_config_no_warnings(self):
        data = {
            "app_name": "MyApp",
            "audience": "technical",
            "format": "markdown",
            "language": "en",
        }

        """WHEN validate_config is called"""
        warnings = validate_config(data)

        """THEN no warnings are returned"""
        assert warnings == []

    """GIVEN a config dict containing an unknown key"""

    def test_unknown_key_warns(self):
        data = {"app_name": "X", "unknown_field": "bad"}

        """WHEN validate_config is called"""
        warnings = validate_config(data)

        """THEN a warning is raised for the unknown field"""
        assert any(w.field == "unknown_field" for w in warnings)

    """GIVEN a config dict with an invalid audience value"""

    def test_invalid_audience_warns(self):
        data = {"audience": "invalid_audience"}

        """WHEN validate_config is called"""
        warnings = validate_config(data)

        """THEN a warning is raised for the audience field"""
        assert any(w.field == "audience" for w in warnings)

    """GIVEN a config dict with an invalid format value"""

    def test_invalid_format_warns(self):
        data = {"format": "html"}

        """WHEN validate_config is called"""
        warnings = validate_config(data)

        """THEN a warning is raised for the format field"""
        assert any(w.field == "format" for w in warnings)

    """GIVEN a config dict with an invalid language value"""

    def test_invalid_language_warns(self):
        data = {"language": "xx"}

        """WHEN validate_config is called"""
        warnings = validate_config(data)

        """THEN a warning is raised for the language field"""
        assert any(w.field == "language" for w in warnings)

    """GIVEN a config dict where repos is a string instead of a list"""

    def test_repos_not_list_warns(self):
        data = {"repos": "not-a-list"}

        """WHEN validate_config is called"""
        warnings = validate_config(data)

        """THEN a warning is raised for the repos field"""
        assert any(w.field == "repos" for w in warnings)

    """GIVEN a config dict where a boolean field has a string value"""

    def test_bool_field_type_warns(self):
        data = {"show_authors": "yes"}

        """WHEN validate_config is called"""
        warnings = validate_config(data)

        """THEN a warning is raised for the show_authors field"""
        assert any(w.field == "show_authors" for w in warnings)

    """GIVEN a config dict where a string field has an integer value"""

    def test_string_field_type_warns(self):
        data = {"branch": 123}

        """WHEN validate_config is called"""
        warnings = validate_config(data)

        """THEN a warning is raised for the branch field"""
        assert any(w.field == "branch" for w in warnings)

    """GIVEN each valid audience value from the allowed set"""

    def test_all_valid_audiences_accepted(self):
        """WHEN the test exercises all valid audiences accepted"""
        for aud in _VALID_AUDIENCES:
            """WHEN validate_config is called with that audience."""
            """THEN no warnings are returned."""
            assert validate_config({"audience": aud}) == []

    """GIVEN each valid format value from the allowed set"""

    def test_all_valid_formats_accepted(self):
        """WHEN the test exercises all valid formats accepted"""
        for fmt in _VALID_FORMATS:
            """WHEN validate_config is called with that format."""
            """THEN no warnings are returned."""
            assert validate_config({"format": fmt}) == []

    """GIVEN each valid language value from the allowed set"""

    def test_all_valid_languages_accepted(self):
        """WHEN the test exercises all valid languages accepted"""
        for lang in _VALID_LANGUAGES:
            """WHEN validate_config is called with that language."""
            """THEN no warnings are returned."""
            assert validate_config({"language": lang}) == []

    """GIVEN +"""

    def test_empty_config_no_warnings(self):
        """THEN no warnings are returned"""
        """WHEN validate_config is called with an empty dict"""
        assert validate_config({}) == []


class TestConfigSanitisation:
    """Scenarios for config sanitisation of invalid enum values."""

    """GIVEN a config dict with an invalid audience value"""

    def test_invalid_audience_sanitised(self):
        data = {"audience": "bad_value"}

        """WHEN _dict_to_config converts it to a FileConfig"""
        cfg = _dict_to_config(data)

        """THEN the audience is sanitised to empty string with warnings"""
        assert cfg.audience == ""
        assert len(cfg.warnings) > 0

    """GIVEN a config dict with an invalid format value"""

    def test_invalid_format_sanitised(self):
        data = {"format": "html"}

        """WHEN _dict_to_config converts it to a FileConfig"""
        cfg = _dict_to_config(data)

        """THEN the format is sanitised to empty string"""
        assert cfg.format == ""

    """GIVEN a config dict with an invalid language value"""

    def test_invalid_language_sanitised(self):
        data = {"language": "zz"}

        """WHEN _dict_to_config converts it to a FileConfig"""
        cfg = _dict_to_config(data)

        """THEN the language is sanitised to empty string"""
        assert cfg.language == ""

    """GIVEN a config dict with all valid enum values"""

    def test_valid_values_preserved(self):
        data = {"audience": "executive", "format": "pdf", "language": "de"}

        """WHEN _dict_to_config converts it to a FileConfig"""
        cfg = _dict_to_config(data)

        """THEN the original values are preserved"""
        assert cfg.audience == "executive"
        assert cfg.format == "pdf"
        assert cfg.language == "de"

    """GIVEN a config dict with multiple invalid entries"""

    def test_warnings_attached_to_config(self):
        data = {"audience": "bad", "mystery_key": True}

        """WHEN _dict_to_config converts it to a FileConfig"""
        cfg = _dict_to_config(data)

        """THEN at least two warnings are attached to the config"""
        assert len(cfg.warnings) >= 2


class TestFileConfigWarningsField:
    """Scenarios for FileConfig warnings field behaviour."""

    """GIVEN +"""

    def test_empty_config_no_warnings(self):
        """WHEN a default FileConfig is created"""
        cfg = FileConfig()

        """THEN the warnings list is empty"""
        assert cfg.warnings == []

    """GIVEN a ConfigWarning with a field and message"""

    def test_config_warning_str(self):
        w = ConfigWarning(field="audience", message="Invalid value")

        """WHEN the warning is converted to a string"""
        """THEN it contains both the field name and the message"""
        assert "audience" in str(w)
        assert "Invalid value" in str(w)


# ── Date-range transparency tests ────────────────────────────────────────────


class TestDateRangeLabel:
    """Scenarios for date range label construction."""

    """GIVEN today's date and a 30-day timedelta"""

    def test_last_30_days_calculation(self):
        """WHEN 30 days are subtracted and converted to ISO format"""
        result = (date.today() - timedelta(days=30)).isoformat()
        expected_approx = date.today() - timedelta(days=30)

        """THEN the ISO string matches the expected date"""
        assert result == expected_approx.isoformat()

    """GIVEN a Settings object with since_date set to 2025-01-15"""

    def test_build_release_range_date_title(self):
        from releasepilot.config.settings import Settings
        from releasepilot.pipeline.orchestrator import build_release_range

        settings = Settings(
            repo_path=".",
            since_date="2025-01-15",
            branch="main",
        )

        """WHEN build_release_range is called"""
        rr = build_release_range(settings)

        """THEN the resulting title contains the since_date"""
        assert "2025-01-15" in rr.title


# ── Config file with validation end-to-end ──────────────────────────────────


class TestConfigFileValidationE2E:
    """Scenarios for end-to-end config file loading with validation."""

    """GIVEN a TOML config file with invalid audience and unknown key"""

    def test_load_config_with_warnings(self, tmp_path):
        from releasepilot.config.file_config import load_config

        toml_content = textwrap.dedent("""\
            app_name = "TestApp"
            audience = "invalid_audience"
            mystery = "key"
        """)
        (tmp_path / ".releasepilot.toml").write_text(toml_content)

        """WHEN load_config reads the file"""
        cfg = load_config(str(tmp_path))

        """THEN app_name is loaded, audience is sanitised, and warnings are present"""
        assert cfg.app_name == "TestApp"
        assert cfg.audience == ""  # Sanitised
        assert len(cfg.warnings) >= 2

    """GIVEN a TOML config file with all valid values"""

    def test_load_valid_config_no_warnings(self, tmp_path):
        from releasepilot.config.file_config import load_config

        toml_content = textwrap.dedent("""\
            app_name = "Good"
            audience = "executive"
            language = "pl"
        """)
        (tmp_path / ".releasepilot.toml").write_text(toml_content)

        """WHEN load_config reads the file"""
        cfg = load_config(str(tmp_path))

        """THEN no warnings are present and values are preserved"""
        assert cfg.warnings == []
        assert cfg.audience == "executive"
        assert cfg.language == "pl"
