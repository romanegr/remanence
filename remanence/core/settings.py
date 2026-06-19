# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Application settings (paths and defaults), stored outside the repository.

User preferences live in ``$XDG_CONFIG_HOME/remanence/settings.yaml`` (default
``~/.config/remanence/settings.yaml``). The GUI Preferences dialog only edits the
:class:`Settings` value defined here, keeping configuration logic in the testable
core. Every read/write is validated against ``settings.schema.json``.
"""

from __future__ import annotations

import io
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from . import schema

SCHEMA_VERSION = 1
APP_DIR_NAME = "remanence"
SETTINGS_FILENAME = "settings.yaml"


@dataclass
class Settings:
    """User-editable application preferences."""

    schema_version: int = SCHEMA_VERSION
    # Paths
    pipelines_path: str = "pipelines.yaml"
    staging_root: str = "staging"
    catalog_root: str | None = None
    blob_stock: str | None = None
    blob_index: str | None = None
    # Acquisition defaults
    default_operator: str = ""
    default_device: str = ""
    default_revolutions: int = 5
    # Photo defaults
    default_media_ratio: str = "5.25"
    jpeg_quality: int = 80
    max_long_edge: int = 2000
    # Interface
    language: str = "fr"
    theme: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def validate(self) -> None:
        schema.validate(self.to_dict(), "settings")


def default_settings_path() -> Path:
    """Return the XDG settings file path (not necessarily existing)."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / APP_DIR_NAME / SETTINGS_FILENAME


def load_settings(path: str | Path | None = None) -> Settings:
    """Load settings from ``path`` (default XDG); return defaults if absent."""
    target = Path(path) if path is not None else default_settings_path()
    if not target.is_file():
        return Settings()
    yaml = YAML(typ="safe")
    with open(target, "rb") as handle:
        data = yaml.load(handle) or {}
    plain = {str(k): v for k, v in data.items()}
    schema.validate(plain, "settings")
    return Settings.from_dict(plain)


def save_settings(settings: Settings, path: str | Path | None = None) -> Path:
    """Validate and atomically write ``settings`` to ``path`` (default XDG)."""
    settings.validate()
    target = Path(path) if path is not None else default_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.dump(settings.to_dict(), buffer)
    _atomic_write(target, buffer.getvalue().encode("utf-8"))
    return target


def _atomic_write(dest: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-", suffix=dest.suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
