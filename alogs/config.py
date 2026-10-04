"""User configuration locations (docs/06, "Configuration")."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir


def config_dir() -> Path:
    """`ALOGS_CONFIG_DIR` overrides the platform default (used by tests)."""
    override = os.environ.get("ALOGS_CONFIG_DIR")
    return Path(override) if override else Path(user_config_dir("alogs", appauthor=False))


def formats_file() -> Path:
    return config_dir() / "formats.toml"


def history_file() -> Path:
    return config_dir() / "history"
