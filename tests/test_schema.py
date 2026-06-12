# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Schema loading and validation tests (no GUI, no hardware)."""

from __future__ import annotations

import copy

import pytest

from jsonschema import Draft202012Validator

from remanence.core import schema
from remanence.core.errors import SchemaValidationError

ZERO_SHA = "0" * 64


def test_every_registered_schema_is_a_valid_metaschema():
    for name in schema.SCHEMA_FILES:
        loaded = schema.load_schema(name)
        assert loaded["properties"]["schema_version"]["const"] == 1
        # Raises if the schema itself is malformed.
        Draft202012Validator.check_schema(loaded)


def test_unknown_schema_name_raises():
    with pytest.raises(SchemaValidationError):
        schema.load_schema("does-not-exist")


def test_nominal_manifest_validates(sample_manifest):
    schema.validate(sample_manifest, "manifest")
    assert schema.is_valid(sample_manifest, "manifest")


def test_manifest_rejects_unknown_decode_status(sample_manifest):
    bad = copy.deepcopy(sample_manifest)
    bad["decode_status"] = "maybe"
    with pytest.raises(SchemaValidationError) as exc:
        schema.validate(bad, "manifest")
    assert "decode_status" in str(exc.value)


def test_manifest_rejects_bad_sha256(sample_manifest):
    bad = copy.deepcopy(sample_manifest)
    bad["files"][0]["sha256"] = "NOTHEX"
    with pytest.raises(SchemaValidationError):
        schema.validate(bad, "manifest")


def test_manifest_rejects_additional_properties(sample_manifest):
    bad = copy.deepcopy(sample_manifest)
    bad["surprise"] = True
    with pytest.raises(SchemaValidationError):
        schema.validate(bad, "manifest")


def test_manifest_requires_at_least_one_file(sample_manifest):
    bad = copy.deepcopy(sample_manifest)
    bad["files"] = []
    with pytest.raises(SchemaValidationError):
        schema.validate(bad, "manifest")


def test_defective_disk_flux_only_manifest_validates():
    """Flux-only, undecodable disk with multiple variants (SOFTWARE-SPEC.md §F3)."""
    manifest = {
        "schema_version": 1,
        "run_id": "2026-06-11_run02",
        "pipeline_id": "gw-c64-1541",
        "captured_by": "operator-id",
        "date_captured": "2026-06-11T15:00:00+02:00",
        "platform_hint": "commodore-c64",
        "acquisition": {
            "method": "greaseweazle",
            "preservation_level": "silver",
        },
        "decode_status": "failed",
        "needs_redecode": True,
        "flux_stable": False,
        "listing_file": None,
        "files": [
            {"temp_name": "flux_read01.scp", "role": "flux", "format": "scp",
             "variant": 1, "best": False, "sha256": ZERO_SHA,
             "read_quality": "12 weak sectors", "upload": True, "tosec_name": None},
            {"temp_name": "flux_read02.scp", "role": "flux", "format": "scp",
             "variant": 2, "best": True, "sha256": ZERO_SHA,
             "read_quality": "9 weak sectors", "upload": True, "tosec_name": None},
        ],
    }
    schema.validate(manifest, "manifest")


@pytest.fixture
def sample_item():
    return {
        "schema_version": 1,
        "ia_identifier": "bards-tale-the-1985-electronic-arts-c64",
        "status": "draft",
        "title": "Bard's Tale, The",
        "kind": "single_title",
        "date": 1985,
        "publisher": "Electronic Arts",
        "platform": "commodore-c64",
        "country": "US",
        "language": "en",
        "copyright_status": "commercial",
        "publish_despite_copyright": False,
        "disks": ["disk-01", "disk-02"],
    }


def test_item_validates(sample_item):
    schema.validate(sample_item, "item")


def test_item_rejects_bad_country(sample_item):
    bad = copy.deepcopy(sample_item)
    bad["country"] = "usa"
    with pytest.raises(SchemaValidationError):
        schema.validate(bad, "item")


def test_item_rejects_unknown_copyright_status(sample_item):
    bad = copy.deepcopy(sample_item)
    bad["copyright_status"] = "abandonware"
    with pytest.raises(SchemaValidationError):
        schema.validate(bad, "item")


def test_contents_validates():
    contents = {
        "schema_version": 1,
        "titles": [
            {"title": "Bard's Tale, The", "date": 1985,
             "publisher": "Electronic Arts", "on_disks": ["disk-01", "disk-02"]},
        ],
    }
    schema.validate(contents, "contents")


def test_disk_validates():
    disk = {
        "schema_version": 1,
        "disk_id": "disk-01",
        "media_type": "Disk 1 of 2",
        "physical": {"media": "5.25 DD", "sides": 1,
                     "write_protected": False, "condition": "good"},
        "label_text": "BARDS TALE DISK 1",
        "acquisition": {
            "method": "greaseweazle",
            "hardware": "Greaseweazle V4 + 5.25 drive",
            "software": "gw 1.21",
            "revolutions": 5,
            "preservation_level": "gold",
            "read_quality": "clean",
            "readlog": "disk-01.readlog.txt",
        },
        "files": [
            {"role": "flux", "format": "scp", "sha256": ZERO_SHA,
             "tosec_name": "Bard's Tale, The (1985)(Electronic Arts)(US)(Disk 1 of 2)[!].scp",
             "upload": True},
        ],
        "listing": "listings/disk-01.txt",
        "photos": ["photos/disk-01-front.jpg"],
    }
    schema.validate(disk, "disk")
