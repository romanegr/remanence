# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""End-to-end no-hardware acceptance: a complete staging run (SOFTWARE-SPEC §11)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from remanence.core import schema
from remanence.core.hashing import sha256_file
from remanence.core.images import EditOps, Keystone
from remanence.core.manifest import load_manifest
from remanence.core.pipelines import load_pipelines
from remanence.core.runner import Runner
from remanence.core.session import DumpSession
from remanence.core.staging import create_run

EXAMPLE = Path(__file__).resolve().parents[1] / "pipelines.example.yaml"


def test_complete_fixture_staging_run(tmp_path):
    """The fixture chain yields a full staging/<run>/: flux + image + normalised
    photo + label + manifest, with a correct sha256 for every produced file and a
    schema-valid manifest."""
    registry = load_pipelines(EXAMPLE)
    pipeline = registry.get("fixture-c64")
    run = create_run(tmp_path, "acceptance01")
    session = DumpSession(run, pipeline, captured_by="ci", platform_hint="commodore-c64")

    # Acquire (no hardware) and attach a keystone-corrected photo.
    session.acquire(Runner(run), {}, best=True, read_quality="clean")
    photo = tmp_path / "front.png"
    cv2.imwrite(str(photo), np.full((1500, 1200, 3), 160, dtype=np.uint8))
    session.add_photo(
        photo, type="front", disk_id="disk-01",
        ops=EditOps(keystone=Keystone(points=[(10, 10), (900, 30), (980, 1100), (40, 1080)],
                                      ratio="5.25")),
    )
    session.set_label_text("REMANENCE DEMO")
    session.set_physical(media="5.25 DD", sides=1, write_protected=False, condition="good")

    manifest_path = session.write_manifest()

    # All expected artefacts are present in the run directory.
    assert (run.path / "flux_read01.scp").exists()
    assert (run.path / "image01.d64").exists()
    assert (run.path / "photos" / "disk-01-front.jpg").exists()
    assert (run.path / "label.txt").read_text() == "REMANENCE DEMO"
    assert manifest_path.name == "manifest.yaml"

    # The manifest validates and its hashes match the files on disk.
    manifest = load_manifest(manifest_path)
    schema.validate(manifest, "manifest")
    for entry in manifest["files"]:
        assert entry["sha256"] == sha256_file(run.path / entry["temp_name"])
    assert manifest["acquisition"]["preservation_level"] == "gold"
    assert manifest["photos"][0]["edits"]["keystone"] is True
