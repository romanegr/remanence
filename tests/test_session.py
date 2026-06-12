# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""DumpSession orchestration tests (no GUI, no hardware)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from remanence.core.images import EditOps
from remanence.core.manifest import load_manifest
from remanence.core.pipelines import load_pipelines
from remanence.core.runner import Runner
from remanence.core.session import DumpSession
from remanence.core.staging import create_run

EXAMPLE = Path(__file__).resolve().parents[1] / "pipelines.example.yaml"


def _session(tmp_path, pipeline_id="fixture-c64"):
    registry = load_pipelines(EXAMPLE)
    pipeline = registry.get(pipeline_id)
    run = create_run(tmp_path, "run01")
    session = DumpSession(run, pipeline, captured_by="tester", platform_hint="commodore-c64")
    return session, Runner(run)


def test_nominal_session_writes_gold_manifest(tmp_path):
    session, runner = _session(tmp_path)
    session.acquire(runner, {}, best=True, read_quality="clean")
    session.set_physical(media="5.25 DD", sides=1, write_protected=False, condition="good")
    session.set_label_text("REMANENCE DEMO")

    verdict = session.assessment()
    assert verdict.preservation_level == "gold"
    assert verdict.state == "decoded"

    path = session.write_manifest()
    manifest = load_manifest(path)
    assert manifest["acquisition"]["preservation_level"] == "gold"
    assert manifest["label_text_file"] == "label.txt"
    assert (session.run.path / "label.txt").exists()


def test_reread_keeps_multiple_variants(tmp_path):
    session, runner = _session(tmp_path)
    session.acquire(runner, {})
    session.acquire(runner, {})
    session.acquire(runner, {}, best=True)
    assert len(session.flux) == 3
    manifest = load_manifest(session.write_manifest())
    flux = [f for f in manifest["files"] if f["role"] == "flux"]
    assert len(flux) == 3
    assert sum(1 for f in flux if f["best"]) == 1
    assert len({f["sha256"] for f in flux}) == 1  # same fixture bytes


def test_flux_only_after_discarding_image(tmp_path):
    session, runner = _session(tmp_path)
    session.acquire(runner, {}, best=True)
    session.discard_image()      # operator keeps flux only (F3)
    session.flux_stable = False
    verdict = session.assessment()
    assert verdict.preservation_level == "silver"
    assert verdict.decode_status == "failed"
    assert verdict.needs_redecode is True
    assert verdict.state == "unstable"

    manifest = load_manifest(session.write_manifest())
    assert manifest["needs_redecode"] is True
    assert not any(f["role"] == "image" for f in manifest["files"])


def test_add_photo_normalises_into_run(tmp_path):
    session, runner = _session(tmp_path)
    session.acquire(runner, {}, best=True)

    photo = tmp_path / "front.png"
    cv2.imwrite(str(photo), np.full((1200, 900, 3), 180, dtype=np.uint8))
    rel = session.add_photo(photo, type="front", disk_id="disk-01",
                            ops=EditOps(brightness=5))
    assert rel == "photos/disk-01-front.jpg"
    assert (session.run.path / rel).exists()

    manifest = load_manifest(session.write_manifest())
    assert manifest["photos"][0]["type"] == "front"
    assert manifest["photos"][0]["edits"]["brightness"] == 5
