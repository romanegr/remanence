# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Staging run tests: atomic writes, naming, safety, reopening."""

from __future__ import annotations

import pytest

from remanence.core.errors import StagingError
from remanence.core.staging import create_run, reopen_run


def test_create_run_makes_directory(tmp_path):
    run = create_run(tmp_path, "2026-06-11_run01")
    assert run.path.is_dir()
    assert run.run_id == "2026-06-11_run01"


def test_create_run_refuses_existing(tmp_path):
    create_run(tmp_path, "run01")
    with pytest.raises(StagingError):
        create_run(tmp_path, "run01")


def test_auto_run_id_is_unique(tmp_path):
    first = create_run(tmp_path)
    second = create_run(tmp_path)
    assert first.run_id != second.run_id


def test_alloc_temp_flux_naming(tmp_path):
    run = create_run(tmp_path, "run01")
    assert run.alloc_temp("flux", "scp") == "flux_read01.scp"
    assert run.alloc_temp("flux", ".scp") == "flux_read02.scp"
    assert run.alloc_temp("image", "d64") == "image01.d64"


def test_write_atomic_creates_file(tmp_path):
    run = create_run(tmp_path, "run01")
    path = run.write_atomic("label.txt", "BARDS TALE")
    assert path.read_text() == "BARDS TALE"


def test_write_atomic_refuses_silent_overwrite(tmp_path):
    run = create_run(tmp_path, "run01")
    run.write_atomic("label.txt", "first")
    with pytest.raises(StagingError):
        run.write_atomic("label.txt", "second")
    # Explicit overwrite is allowed.
    run.write_atomic("label.txt", "third", overwrite=True)
    assert (run.path / "label.txt").read_text() == "third"


def test_write_atomic_leaves_no_temp_files(tmp_path):
    run = create_run(tmp_path, "run01")
    run.write_atomic("photos/front.jpg", b"\xff\xd8\xff")
    leftovers = list(run.path.rglob(".tmp-*"))
    assert leftovers == []


def test_write_outside_run_is_refused(tmp_path):
    run = create_run(tmp_path, "run01")
    with pytest.raises(StagingError):
        run.write_atomic("../escape.txt", "nope")
    with pytest.raises(StagingError):
        run.write_atomic("/etc/passwd", "nope")


def test_add_file_copies_atomically(tmp_path):
    run = create_run(tmp_path, "run01")
    src = tmp_path / "source.scp"
    src.write_bytes(b"flux")
    dest = run.add_file(src, "flux_read01.scp")
    assert dest.read_bytes() == b"flux"


def test_reopen_run(tmp_path):
    run = create_run(tmp_path, "run01")
    run.write_atomic("label.txt", "x")
    reopened = reopen_run(run.path)
    assert reopened.run_id == "run01"
    reopened.write_atomic("note.txt", "added later")
    assert (run.path / "note.txt").exists()


def test_reopen_missing_run_raises(tmp_path):
    with pytest.raises(StagingError):
        reopen_run(tmp_path / "nope")
