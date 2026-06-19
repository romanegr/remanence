# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Settings load/save/validation tests (no GUI)."""

from __future__ import annotations

import pytest

from remanence.core import schema
from remanence.core.errors import SchemaValidationError
from remanence.core.settings import (
    Settings,
    default_settings_path,
    load_settings,
    save_settings,
)


def test_defaults_validate():
    Settings().validate()
    assert schema.is_valid(Settings().to_dict(), "settings")


def test_round_trip(tmp_path):
    path = tmp_path / "settings.yaml"
    original = Settings(
        staging_root="/data/staging",
        catalog_root="/data/catalog",
        blob_stock="/data/blobs",
        default_operator="rn",
        default_revolutions=7,
        default_media_ratio="3.5",
        jpeg_quality=90,
        language="en",
        theme="dark",
    )
    save_settings(original, path)
    loaded = load_settings(path)
    assert loaded == original


def test_load_missing_returns_defaults(tmp_path):
    loaded = load_settings(tmp_path / "nope.yaml")
    assert loaded == Settings()


def test_default_path_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_settings_path() == tmp_path / "remanence" / "settings.yaml"


def test_save_creates_parent_dirs(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = save_settings(Settings())
    assert path.is_file()
    assert path == tmp_path / "remanence" / "settings.yaml"


def test_invalid_theme_rejected():
    bad = Settings(theme="neon")
    with pytest.raises(SchemaValidationError):
        bad.validate()


def test_load_rejects_invalid_file(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("schema_version: 1\njpeg_quality: 999\n")
    with pytest.raises(SchemaValidationError):
        load_settings(path)


def test_unknown_keys_ignored_on_load(tmp_path):
    # Forward-compatible: unknown keys present in the dict are dropped by from_dict,
    # but schema validation runs first and would reject them, so we test from_dict.
    s = Settings.from_dict({"staging_root": "x", "mystery": 1})
    assert s.staging_root == "x"
    assert not hasattr(s, "mystery")
