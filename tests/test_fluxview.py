# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Flux visualisation tests: SCP parsing, histogram, track map (F11)."""

from __future__ import annotations

import numpy as np
import pytest

from remanence.core import fluxview
from remanence.fixtures import asset_path


def _capture():
    return fluxview.parse_scp(asset_path("fixture_disk.scp"))


def test_parse_scp_header_and_tracks():
    cap = _capture()
    assert cap.num_revolutions == 3
    assert len(cap.tracks) == 4
    assert cap.tick_ns == 25.0
    assert all(len(t.revolutions) == 3 for t in cap.tracks)


def test_parse_rejects_non_scp(tmp_path):
    bad = tmp_path / "not.scp"
    bad.write_bytes(b"XXXX" + b"\x00" * 1000)
    with pytest.raises(ValueError):
        fluxview.parse_scp(bad)


def test_histogram_reveals_two_cell_widths():
    cap = _capture()
    counts, edges = fluxview.flux_histogram(cap, bins=64)
    # The fixture alternates 1000 ns and 2000 ns cells -> two populated bins.
    assert int((counts > 0).sum()) == 2
    assert counts.sum() == cap.all_intervals().size


def test_histogram_empty_capture_is_safe():
    empty = fluxview.ScpCapture(version=1, num_revolutions=0, start_track=0,
                                end_track=0, tick_ns=25.0, tracks=[])
    counts, edges = fluxview.flux_histogram(empty, bins=16)
    assert counts.sum() == 0
    assert len(edges) == 17


def test_track_map_shape_and_density():
    cap = _capture()
    tm = fluxview.track_map(cap, angular_bins=180, revolution=0)
    assert tm.shape == (4, 180)
    # One revolution of 256 transitions per track.
    assert tm.sum() == 4 * 256


def test_compare_variants_summary():
    cap = _capture()
    result = fluxview.compare_variants([cap, cap])
    assert len(result["variants"]) == 2
    assert result["variants"][0]["transitions"] == cap.all_intervals().size
    assert "note" in result
