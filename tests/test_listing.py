# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Listing extraction tests (native d64 path + error handling)."""

from __future__ import annotations

import pytest

from remanence.core import listing
from remanence.core.errors import PreflightError, RemanenceError
from remanence.fixtures import asset_path


def test_extract_d64_listing():
    text = listing.extract_listing(asset_path("fixture_disk.d64"))
    assert "REMANENCE DEMO" in text
    assert "HELLO" in text
    assert "LOADER" in text
    assert "BLOCKS FREE" in text


def test_unknown_format_raises(tmp_path):
    weird = tmp_path / "disk.xyz"
    weird.write_bytes(b"nope")
    with pytest.raises(RemanenceError):
        listing.extract_listing(weird)


def test_missing_image_raises(tmp_path):
    with pytest.raises(RemanenceError):
        listing.extract_listing(tmp_path / "ghost.d64")


def test_ibm_fallback_requires_tool(tmp_path, monkeypatch):
    img = tmp_path / "disk.img"
    img.write_bytes(b"\x00" * 1024)
    monkeypatch.setattr(listing.shutil, "which", lambda name: None)
    with pytest.raises(PreflightError):
        listing.extract_listing(img)
