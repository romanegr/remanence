# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Flux visualisation: parse SCP captures into a flux-interval histogram and a
track map (SOFTWARE-SPEC.md §F11, v1 = histogram + density map).

The SCP (SuperCard Pro) container is documented; this parser reads the header,
the track offset table and per-revolution flux data, converting raw tick counts
into nanosecond intervals. Deep cell decoding is out of scope (defer to HxC/Aufit).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SCP_MAGIC = b"SCP"
_HEADER_SIZE = 16
_TRACK_TABLE_ENTRIES = 168
_BASE_TICK_NS = 25.0  # resolution 0 => 25 ns per tick


@dataclass
class TrackFlux:
    track: int
    # One ndarray of flux intervals (nanoseconds) per revolution.
    revolutions: list[np.ndarray] = field(default_factory=list)

    def all_intervals(self) -> np.ndarray:
        if not self.revolutions:
            return np.array([], dtype=np.float64)
        return np.concatenate(self.revolutions)


@dataclass
class ScpCapture:
    version: int
    num_revolutions: int
    start_track: int
    end_track: int
    tick_ns: float
    tracks: list[TrackFlux] = field(default_factory=list)

    def all_intervals(self) -> np.ndarray:
        arrays = [t.all_intervals() for t in self.tracks]
        arrays = [a for a in arrays if a.size]
        return np.concatenate(arrays) if arrays else np.array([], dtype=np.float64)


def parse_scp(path: str | Path) -> ScpCapture:
    """Parse an SCP file into an :class:`ScpCapture`."""
    data = Path(path).read_bytes()
    if data[:3] != SCP_MAGIC:
        raise ValueError("not an SCP file (bad magic)")
    if len(data) < _HEADER_SIZE + _TRACK_TABLE_ENTRIES * 4:
        raise ValueError("SCP file truncated (header/offset table)")

    version = data[3]
    num_revolutions = data[5]
    start_track = data[6]
    end_track = data[7]
    resolution = data[11]
    tick_ns = _BASE_TICK_NS * (resolution + 1)

    offsets = struct.unpack_from(f"<{_TRACK_TABLE_ENTRIES}I", data, _HEADER_SIZE)
    tracks: list[TrackFlux] = []
    for track_no, offset in enumerate(offsets):
        if offset == 0:
            continue
        track = _parse_track(data, offset, track_no, tick_ns)
        if track is not None:
            tracks.append(track)

    return ScpCapture(
        version=version,
        num_revolutions=num_revolutions,
        start_track=start_track,
        end_track=end_track,
        tick_ns=tick_ns,
        tracks=tracks,
    )


def _parse_track(data: bytes, offset: int, track_no: int, tick_ns: float) -> TrackFlux | None:
    if data[offset:offset + 3] != b"TRK":
        return None
    # Header track number lives at offset+3; we trust the table index for ordering.
    revolutions: list[np.ndarray] = []
    rev_index = 0
    while True:
        rev_header = offset + 4 + rev_index * 12
        if rev_header + 12 > len(data):
            break
        _index_time, length, data_offset = struct.unpack_from("<III", data, rev_header)
        if length == 0:
            break
        flux_start = offset + data_offset
        flux_end = flux_start + length * 2
        if flux_end > len(data):
            break
        words = np.frombuffer(data, dtype=">u2", count=length, offset=flux_start)
        revolutions.append(_to_intervals(words, tick_ns))
        rev_index += 1
        # Stop once the next rev header would collide with flux data we just read.
        if offset + 4 + rev_index * 12 >= flux_start:
            # No reliable way to know rev count without it; rely on length==0 sentinel
            # or table bounds. Heuristic guard against runaway loops.
            if rev_index >= 16:
                break
    return TrackFlux(track=track_no, revolutions=revolutions) if revolutions else None


def _to_intervals(words: np.ndarray, tick_ns: float) -> np.ndarray:
    """Convert raw SCP tick words to nanosecond intervals, folding 0-overflows."""
    intervals: list[float] = []
    carry = 0
    for w in words.astype(np.int64):
        if w == 0:
            carry += 0x10000
            continue
        intervals.append((carry + w) * tick_ns)
        carry = 0
    return np.array(intervals, dtype=np.float64)


def flux_histogram(
    capture: ScpCapture,
    *,
    bins: int = 256,
    range_ns: tuple[float, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(counts, bin_edges)`` of all flux intervals (FM/MFM/GCR peaks)."""
    intervals = capture.all_intervals()
    if intervals.size == 0:
        edges = np.linspace(0.0, 1.0, bins + 1)
        return np.zeros(bins, dtype=np.int64), edges
    if range_ns is None:
        range_ns = (float(intervals.min()), float(intervals.max()))
    counts, edges = np.histogram(intervals, bins=bins, range=range_ns)
    return counts, edges


def track_map(capture: ScpCapture, *, angular_bins: int = 360, revolution: int = 0) -> np.ndarray:
    """2D transition-density map: rows = tracks, columns = angular position.

    Each cell holds the number of flux transitions in that angular slice of the
    chosen revolution — bright bands reveal data, gaps reveal weak/missing areas.
    """
    n_tracks = len(capture.tracks)
    grid = np.zeros((n_tracks, angular_bins), dtype=np.float64)
    for row, track in enumerate(capture.tracks):
        if revolution >= len(track.revolutions):
            continue
        intervals = track.revolutions[revolution]
        if intervals.size == 0:
            continue
        # Angular position = cumulative time normalised over the revolution.
        cumulative = np.cumsum(intervals)
        total = cumulative[-1]
        if total <= 0:
            continue
        positions = np.minimum((cumulative / total * angular_bins).astype(int), angular_bins - 1)
        for pos in positions:
            grid[row, pos] += 1
    return grid


def compare_variants(captures: list[ScpCapture]) -> dict:
    """Compare multiple reads of an unstable disk (SOFTWARE-SPEC.md §F11).

    v1 stub: deeper overlay/diff of diverging reads is a later milestone (defer
    expert analysis to HxC/Aufit). Returns coarse per-capture interval statistics
    so callers can already surface gross differences.
    """
    summary = []
    for capture in captures:
        intervals = capture.all_intervals()
        if intervals.size:
            summary.append({
                "tracks": len(capture.tracks),
                "transitions": int(intervals.size),
                "mean_ns": float(intervals.mean()),
                "std_ns": float(intervals.std()),
            })
        else:
            summary.append({"tracks": len(capture.tracks), "transitions": 0,
                            "mean_ns": 0.0, "std_ns": 0.0})
    return {"variants": summary, "note": "overlay/diff deferred to a later milestone"}
