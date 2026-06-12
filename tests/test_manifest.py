# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Manifest builder tests, including the defective-disk multi-flux case."""

from __future__ import annotations

import pytest

from remanence.core.errors import StagingError
from remanence.core.hashing import sha256_bytes
from remanence.core.manifest import ManifestBuilder, load_manifest
from remanence.core.staging import create_run


def _run_with_flux(tmp_path, payloads):
    run = create_run(tmp_path, "2026-06-11_run01")
    names = []
    for payload in payloads:
        name = run.alloc_temp("flux", "scp")
        run.write_atomic(name, payload)
        names.append(name)
    return run, names


def test_nominal_manifest_build_and_write(tmp_path):
    run = create_run(tmp_path, "run01")
    flux = run.alloc_temp("flux", "scp")
    run.write_atomic(flux, b"flux-bytes")
    image = run.alloc_temp("image", "d64")
    run.write_atomic(image, b"image-bytes")

    builder = (
        ManifestBuilder(
            run,
            pipeline_id="gw-c64-1541",
            captured_by="operator-id",
            method="greaseweazle",
            preservation_level="gold",
            platform_hint="commodore-c64",
            revolutions=5,
        )
        .set_decode_status("ok", needs_redecode=False, flux_stable=True)
        .set_physical(media="5.25 DD", sides=1, write_protected=False, condition="good")
        .add_flux_variant(flux, variant=1, best=True, read_quality="clean")
        .set_image(image, fmt="d64")
        .add_photo("photos/front.jpg", type="front", edits={"keystone": True})
    )
    manifest = builder.build()
    assert manifest["decode_status"] == "ok"
    assert manifest["files"][0]["sha256"] == sha256_bytes(b"flux-bytes")
    assert manifest["files"][1]["sha256"] == sha256_bytes(b"image-bytes")

    path = builder.write()
    assert path.exists()
    reloaded = load_manifest(path)
    assert reloaded["run_id"] == "run01"
    assert reloaded["files"][0]["sha256"] == sha256_bytes(b"flux-bytes")


def test_defective_disk_multi_flux_no_image(tmp_path):
    run, names = _run_with_flux(tmp_path, [b"read-one", b"read-two", b"read-three"])
    builder = ManifestBuilder(
        run,
        pipeline_id="gw-c64-1541",
        captured_by="operator-id",
        method="greaseweazle",
        preservation_level="silver",
    ).set_decode_status("failed", needs_redecode=True, flux_stable=False)
    builder.add_flux_variant(names[0], variant=1, best=False, read_quality="12 weak sectors")
    builder.add_flux_variant(names[1], variant=2, best=True, read_quality="9 weak sectors")
    builder.add_flux_variant(names[2], variant=3, best=False, read_quality="15 weak sectors")

    manifest = builder.build()
    assert manifest["decode_status"] == "failed"
    assert manifest["needs_redecode"] is True
    flux_entries = [f for f in manifest["files"] if f["role"] == "flux"]
    assert len(flux_entries) == 3
    assert sum(1 for f in flux_entries if f["best"]) == 1
    # Each variant has its own distinct hash.
    assert len({f["sha256"] for f in flux_entries}) == 3
    assert not any(f["role"] == "image" for f in manifest["files"])


def test_build_requires_at_least_one_file(tmp_path):
    run = create_run(tmp_path, "run01")
    builder = ManifestBuilder(
        run, pipeline_id="p", captured_by="op",
        method="greaseweazle", preservation_level="bronze",
    )
    with pytest.raises(StagingError):
        builder.build()


def test_build_rejects_missing_referenced_file(tmp_path):
    run = create_run(tmp_path, "run01")
    builder = ManifestBuilder(
        run, pipeline_id="p", captured_by="op",
        method="greaseweazle", preservation_level="silver",
    ).add_flux_variant("ghost.scp", variant=1)
    with pytest.raises(StagingError):
        builder.build()
