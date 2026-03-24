"""Centralized logging configuration."""

import json
import logging
import os
import sys


class StructuredFormatter(logging.Formatter):
    """Formatter that appends structured key=value extras to log lines."""

    def format(self, record: logging.LogRecord) -> str:
        extras = ""
        for key in ("request_path", "repo_name", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                extras += f" {key}={val}"
        base = super().format(record)
        return f"{base}{extras}" if extras else base


class JSONFormatter(logging.Formatter):
    """Formatter that outputs log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_path", "repo_name", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                log_obj[key] = val
        if record.exc_info and record.exc_info[1]:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under ``releasepilot.<name>``."""
    logger = logging.getLogger(f"releasepilot.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            StructuredFormatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger


def configure_root_logger(verbose: bool = False) -> None:
    """Set up the root ``releasepilot`` logger.

    When the ``RELEASEPILOT_LOG_FORMAT`` env var is set to ``json``,
    output is JSON lines suitable for log aggregators.
    """
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger("releasepilot")
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        use_json = os.environ.get("RELEASEPILOT_LOG_FORMAT", "").lower() == "json"
        if use_json:
            handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
        else:
            handler.setFormatter(
                StructuredFormatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
        root.addHandler(handler)
