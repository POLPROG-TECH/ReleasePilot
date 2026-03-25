"""Configuration file support for ReleasePilot.

Loads defaults from JSON or TOML config files, searched in order:
  1. .releasepilot.json  (project-local, recommended)
  2. releasepilot.json   (project-local)
  3. .releasepilot.toml  (project-local)
  4. releasepilot.toml   (project-local)
  5. pyproject.toml       [tool.releasepilot] section
  6. ~/.config/releasepilot/config.json  (user-level)

CLI options always override config-file values.
Missing or empty config files are silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_CONFIG_FILENAMES = (".releasepilot.toml", "releasepilot.toml")
_JSON_CONFIG_FILENAMES = (".releasepilot.json", "releasepilot.json")
_USER_CONFIG_DIR = Path.home() / ".config" / "releasepilot"

# ── Schema definitions ──────────────────────────────────────────────────────

_VALID_AUDIENCES = {
    "technical",
    "user",
    "summary",
    "changelog",
    "customer",
    "executive",
    "narrative",
    "customer-narrative",
}
_VALID_FORMATS = {"markdown", "plaintext", "json", "pdf", "docx"}
_VALID_LANGUAGES = {"en", "pl", "de", "fr", "es", "it", "pt", "nl", "uk", "cs"}

_KNOWN_KEYS = {
    "app_name",
    "app-name",
    "audience",
    "format",
    "language",
    "branch",
    "title",
    "version",
    "show_authors",
    "show-authors",
    "show_hashes",
    "show-hashes",
    "accent_color",
    "accent-color",
    "repos",
    "output_dir",
    "output-dir",
    "overwrite",
    "export_formats",
    "export-formats",
    "ci",
    "schema_version",
    "schema-version",
    "gitlab_url",
    "gitlab-url",
    "gitlab_token",
    "gitlab-token",
    "gitlab_project",
    "gitlab-project",
    "gitlab_ssl_verify",
    "gitlab-ssl-verify",
    "github_token",
    "github-token",
    "github_owner",
    "github-owner",
    "github_repo",
    "github-repo",
    "github_url",
    "github-url",
    "github_ssl_verify",
    "github-ssl-verify",
    "multi_repo_sources",
    "multi-repo-sources",
}


@dataclass
class ConfigWarning:
    """A non-fatal validation issue in a config file."""

    field: str
    message: str

    def __str__(self) -> str:
        return f"Config: '{self.field}' — {self.message}"


@dataclass
class CIConfig:
    """CI/CD-specific configuration."""

    enabled: bool = False
    artifact_name: str = "release-notes"
    fail_on_empty: bool = False
    attach_to_release: bool = False


@dataclass
class FileConfig:
    """Parsed configuration from a config file."""

    app_name: str = ""
    audience: str = ""
    format: str = ""
    language: str = ""
    branch: str = ""
    title: str = ""
    version: str = ""
    show_authors: bool = False
    show_hashes: bool = False
    accent_color: str = ""
    repos: list[str] = field(default_factory=list)
    output_dir: str = ""
    overwrite: bool = False
    export_formats: list[str] = field(default_factory=list)
    ci: CIConfig = field(default_factory=CIConfig)
    gitlab_ssl_verify: bool = True
    github_ssl_verify: bool = True
    source: str = ""  # Path to the config file (for diagnostics)
    warnings: list[ConfigWarning] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.app_name,
                self.audience,
                self.format,
                self.language,
                self.branch,
                self.title,
                self.version,
                self.repos,
                self.output_dir,
                self.overwrite,
                self.export_formats,
                self.ci.enabled,
            ]
        )


def validate_config(data: dict) -> list[ConfigWarning]:
    """Validate a raw config dict and return warnings for any issues.

    Does NOT raise — collects all problems as ConfigWarning objects.
    """
    warnings: list[ConfigWarning] = []

    # Check for unknown keys
    for key in data:
        if key == "$schema":
            continue  # JSON Schema reference — always allowed
        if key not in _KNOWN_KEYS:
            warnings.append(
                ConfigWarning(
                    field=key,
                    message=f"Unknown config key. Valid keys: {', '.join(sorted(_KNOWN_KEYS - {'app-name', 'show-authors', 'show-hashes'}))}",
                )
            )

    # Validate enum-like fields
    audience = data.get("audience", "")
    if audience and str(audience) not in _VALID_AUDIENCES:
        warnings.append(
            ConfigWarning(
                field="audience",
                message=f"Invalid value '{audience}'. Must be one of: {', '.join(sorted(_VALID_AUDIENCES))}",
            )
        )

    fmt = data.get("format", "")
    if fmt and str(fmt) not in _VALID_FORMATS:
        warnings.append(
            ConfigWarning(
                field="format",
                message=f"Invalid value '{fmt}'. Must be one of: {', '.join(sorted(_VALID_FORMATS))}",
            )
        )

    lang = data.get("language", "")
    if lang and str(lang) not in _VALID_LANGUAGES:
        warnings.append(
            ConfigWarning(
                field="language",
                message=f"Invalid value '{lang}'. Must be one of: {', '.join(sorted(_VALID_LANGUAGES))}",
            )
        )

    # Validate types
    repos = data.get("repos")
    if repos is not None and not isinstance(repos, list):
        warnings.append(
            ConfigWarning(
                field="repos",
                message=f"Expected a list, got {type(repos).__name__}.",
            )
        )

    export_formats = data.get("export_formats", data.get("export-formats"))
    if export_formats is not None:
        if not isinstance(export_formats, list):
            warnings.append(
                ConfigWarning(
                    field="export_formats",
                    message=f"Expected a list, got {type(export_formats).__name__}.",
                )
            )
        else:
            for ef in export_formats:
                if str(ef) not in _VALID_FORMATS:
                    warnings.append(
                        ConfigWarning(
                            field="export_formats",
                            message=f"Invalid format '{ef}'. Must be one of: {', '.join(sorted(_VALID_FORMATS))}",
                        )
                    )

    ci_section = data.get("ci")
    if ci_section is not None:
        if not isinstance(ci_section, dict):
            warnings.append(
                ConfigWarning(
                    field="ci",
                    message=f"Expected an object, got {type(ci_section).__name__}.",
                )
            )
        else:
            _ci_known_keys = {
                "enabled",
                "artifact_name",
                "artifact-name",
                "fail_on_empty",
                "fail-on-empty",
                "attach_to_release",
                "attach-to-release",
            }
            for key in ci_section:
                if key not in _ci_known_keys:
                    warnings.append(
                        ConfigWarning(
                            field=f"ci.{key}",
                            message="Unknown CI config key.",
                        )
                    )

    for bool_key in ("show_authors", "show-authors", "show_hashes", "show-hashes", "overwrite"):
        val = data.get(bool_key)
        if val is not None and not isinstance(val, bool):
            warnings.append(
                ConfigWarning(
                    field=bool_key,
                    message=f"Expected a boolean (true/false), got {type(val).__name__}.",
                )
            )

    for str_key in (
        "app_name",
        "app-name",
        "branch",
        "title",
        "version",
        "output_dir",
        "output-dir",
    ):
        val = data.get(str_key)
        if val is not None and not isinstance(val, str):
            warnings.append(
                ConfigWarning(
                    field=str_key,
                    message=f"Expected a string, got {type(val).__name__}.",
                )
            )

    # Validate accent_color format
    import re as _re

    accent = data.get("accent_color", data.get("accent-color", ""))
    if accent and not _re.match(r"^#[0-9a-fA-F]{6}$", str(accent)):
        warnings.append(
            ConfigWarning(
                field="accent_color",
                message=f"Invalid hex color '{accent}'. Must match #RRGGBB format (e.g. #FB6400).",
            )
        )

    return warnings


def load_config(search_dir: str = ".") -> FileConfig:
    """Search for and load a ReleasePilot config file.

    Search order (first match wins):
      1. .releasepilot.json  (project-local)
      2. releasepilot.json   (project-local)
      3. .releasepilot.toml  (project-local)
      4. releasepilot.toml   (project-local)
      5. pyproject.toml       [tool.releasepilot] section
      6. ~/.config/releasepilot/config.json  (user-level)

    Returns an empty FileConfig if nothing is found.
    """
    base = Path(search_dir).resolve()

    # Try JSON config files first (project-local)
    for name in _JSON_CONFIG_FILENAMES:
        candidate = base / name
        if candidate.is_file():
            cfg = _parse_json(candidate)
            if cfg is not None:
                return cfg

    # Try TOML config files (project-local)
    for name in _CONFIG_FILENAMES:
        candidate = base / name
        if candidate.is_file():
            cfg = _parse_toml(candidate)
            if cfg is not None:
                return cfg

    # Fall back to pyproject.toml [tool.releasepilot]
    pyproject = base / "pyproject.toml"
    if pyproject.is_file():
        cfg = _parse_pyproject(pyproject)
        if not cfg.is_empty:
            return cfg

    # Fall back to user-level config
    user_config = _USER_CONFIG_DIR / "config.json"
    if user_config.is_file():
        cfg = _parse_json(user_config)
        if cfg is not None:
            return cfg

    return FileConfig()


def _parse_toml(path: Path) -> FileConfig | None:
    """Parse a standalone .releasepilot.toml file.  Returns None on parse error."""
    data = _read_toml(path)
    if data is None:
        return None
    return _dict_to_config(data, source=str(path))


def _parse_pyproject(path: Path) -> FileConfig:
    """Parse [tool.releasepilot] from pyproject.toml."""
    data = _read_toml(path)
    if data is None:
        return FileConfig()
    section = data.get("tool", {}).get("releasepilot", {})
    if not section:
        return FileConfig()
    return _dict_to_config(section, source=str(path))


def _parse_json(path: Path) -> FileConfig | None:
    """Parse a .releasepilot.json config file.  Returns None on parse error."""
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return _dict_to_config(data, source=str(path))


def _read_toml(path: Path) -> dict | None:
    """Read a TOML file, returning None on any error.

    Logs a warning when the file exists but cannot be parsed so that
    configuration typos don't go unnoticed.
    """
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover — Python < 3.11
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return None

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("releasepilot.config").warning(
            "Failed to parse TOML file %s: %s",
            path,
            exc,
        )
        return None


def _dict_to_config(data: dict, *, source: str = "") -> FileConfig:
    """Map a dict (from TOML) to a FileConfig, with validation."""
    warnings = validate_config(data)

    repos_raw = data.get("repos", [])
    repos = [str(r) for r in repos_raw] if isinstance(repos_raw, list) else []

    ef_raw = data.get("export_formats", data.get("export-formats", []))
    export_formats = (
        [str(f) for f in ef_raw if str(f) in _VALID_FORMATS] if isinstance(ef_raw, list) else []
    )

    ci_raw = data.get("ci", {})
    ci_cfg = CIConfig()
    if isinstance(ci_raw, dict):
        ci_cfg = CIConfig(
            enabled=bool(ci_raw.get("enabled", False)),
            artifact_name=str(
                ci_raw.get("artifact_name", ci_raw.get("artifact-name", "release-notes"))
            ),
            fail_on_empty=bool(ci_raw.get("fail_on_empty", ci_raw.get("fail-on-empty", False))),
            attach_to_release=bool(
                ci_raw.get("attach_to_release", ci_raw.get("attach-to-release", False))
            ),
        )

    # Sanitise enum fields — use value only if valid, else empty string
    audience = str(data.get("audience", ""))
    if audience and audience not in _VALID_AUDIENCES:
        audience = ""

    fmt = str(data.get("format", ""))
    if fmt and fmt not in _VALID_FORMATS:
        fmt = ""

    lang = str(data.get("language", ""))
    if lang and lang not in _VALID_LANGUAGES:
        lang = ""

    # SSL verify flags (default True for safety)
    def _ssl_bool(val: object) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() not in ("0", "false", "no")
        return True

    gitlab_ssl_val = data.get("gitlab_ssl_verify", data.get("gitlab-ssl-verify", True))
    github_ssl_val = data.get("github_ssl_verify", data.get("github-ssl-verify", True))

    return FileConfig(
        app_name=str(data.get("app_name", data.get("app-name", ""))),
        audience=audience,
        format=fmt,
        language=lang,
        branch=str(data.get("branch", "")),
        title=str(data.get("title", "")),
        version=str(data.get("version", "")),
        show_authors=bool(data.get("show_authors", data.get("show-authors", False))),
        show_hashes=bool(data.get("show_hashes", data.get("show-hashes", False))),
        accent_color=str(data.get("accent_color", data.get("accent-color", ""))),
        repos=repos,
        output_dir=str(data.get("output_dir", data.get("output-dir", ""))),
        overwrite=bool(data.get("overwrite", False)),
        export_formats=export_formats,
        ci=ci_cfg,
        gitlab_ssl_verify=_ssl_bool(gitlab_ssl_val),
        github_ssl_verify=_ssl_bool(github_ssl_val),
        source=source,
        warnings=warnings,
    )
