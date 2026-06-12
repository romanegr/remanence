# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Catalogue (Library mode) tests: browse, filter, integrity by sha256."""

from __future__ import annotations

import pytest
from ruamel.yaml import YAML

from remanence.core.catalog import BlobIndex, open_catalog
from remanence.core.errors import RemanenceError
from remanence.core.hashing import sha256_file
from remanence.fixtures import asset_path

YAML_RT = YAML()


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        YAML_RT.dump(data, handle)


def _build_catalog(tmp_path, blob_sha):
    item_dir = tmp_path / "catalog" / "commodore-c64" / "demo-1985-acme-c64"
    _write_yaml(item_dir / "item.yaml", {
        "schema_version": 1,
        "status": "ready",
        "title": "Demo Game",
        "kind": "single_title",
        "platform": "commodore-c64",
        "publisher": "Acme",
        "copyright_status": "freeware",
        "disks": ["disk-01"],
    })
    _write_yaml(item_dir / "disks" / "disk-01.yaml", {
        "schema_version": 1,
        "disk_id": "disk-01",
        "acquisition": {"method": "greaseweazle", "preservation_level": "gold"},
        "files": [
            {"role": "image", "format": "d64", "sha256": blob_sha,
             "tosec_name": "Demo Game (1985)(Acme)[!].d64", "upload": True},
        ],
    })
    return tmp_path / "catalog"


def test_browse_and_filter(tmp_path):
    blob = asset_path("fixture_disk.d64")
    sha = sha256_file(blob)
    root = _build_catalog(tmp_path, sha)
    catalog = open_catalog(root, BlobIndex({sha: str(blob)}))

    items = list(catalog.iter_items())
    assert len(items) == 1
    assert items[0].title == "Demo Game"
    assert catalog.filter(platform="commodore-c64")
    assert catalog.filter(status="ready")
    assert catalog.filter(text="demo")
    assert catalog.filter(platform="apple-ii") == []


def test_get_loads_disks(tmp_path):
    blob = asset_path("fixture_disk.d64")
    sha = sha256_file(blob)
    root = _build_catalog(tmp_path, sha)
    catalog = open_catalog(root, BlobIndex({sha: str(blob)}))
    item = catalog.get("demo-1985-acme-c64")
    assert item.disks[0]["disk_id"] == "disk-01"


def test_integrity_ok(tmp_path):
    blob = asset_path("fixture_disk.d64")
    sha = sha256_file(blob)
    root = _build_catalog(tmp_path, sha)
    catalog = open_catalog(root, BlobIndex({sha: str(blob)}))
    item = catalog.get("demo-1985-acme-c64")
    assert catalog.verify_integrity(item) == []


def test_integrity_missing_blob(tmp_path):
    blob = asset_path("fixture_disk.d64")
    sha = sha256_file(blob)
    root = _build_catalog(tmp_path, sha)
    # Empty index -> blob cannot be resolved.
    catalog = open_catalog(root, BlobIndex({}))
    item = catalog.get("demo-1985-acme-c64")
    issues = catalog.verify_integrity(item)
    assert len(issues) == 1
    assert issues[0].kind == "missing"


def test_integrity_corruption_detected(tmp_path):
    blob = asset_path("fixture_disk.d64")
    sha = sha256_file(blob)
    root = _build_catalog(tmp_path, sha)
    # Index resolves the recorded sha to a *different* file -> silent corruption.
    other = asset_path("fixture_disk.scp")
    catalog = open_catalog(root, BlobIndex({sha: str(other)}))
    item = catalog.get("demo-1985-acme-c64")
    issues = catalog.verify_integrity(item)
    assert len(issues) == 1
    assert issues[0].kind == "corrupted"


def test_open_missing_catalog_raises(tmp_path):
    with pytest.raises(RemanenceError):
        open_catalog(tmp_path / "nope")
