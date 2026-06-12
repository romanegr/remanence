# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Shared pytest fixtures and constants."""

from __future__ import annotations

from pathlib import Path

import pytest

# A syntactically valid sha256 (all zeros) for building manifest fixtures.
ZERO_SHA = "0" * 64


@pytest.fixture
def sample_manifest() -> dict:
    """A nominal, schema-valid manifest (decoded healthy disk)."""
    return {
        "schema_version": 1,
        "run_id": "2026-06-11_run01",
        "pipeline_id": "gw-c64-1541",
        "captured_by": "operator-id",
        "date_captured": "2026-06-11T14:32:00+02:00",
        "platform_hint": "commodore-c64",
        "acquisition": {
            "method": "greaseweazle",
            "hardware": "Greaseweazle V4 + 5.25 drive",
            "software": "gw 1.21",
            "revolutions": 5,
            "preservation_level": "gold",
        },
        "decode_status": "ok",
        "needs_redecode": False,
        "flux_stable": True,
        "physical": {
            "media": "5.25 DD",
            "sides": 1,
            "write_protected": False,
            "condition": "good",
        },
        "label_text_file": "label.txt",
        "listing_file": "listing.txt",
        "files": [
            {
                "temp_name": "flux_read01.scp",
                "role": "flux",
                "format": "scp",
                "variant": 1,
                "best": True,
                "sha256": ZERO_SHA,
                "read_quality": "clean",
                "upload": True,
                "tosec_name": None,
            },
            {
                "temp_name": "image01.d64",
                "role": "image",
                "format": "d64",
                "sha256": ZERO_SHA,
                "upload": True,
                "tosec_name": None,
            },
        ],
        "photos": [
            {"file": "photos/front.jpg", "type": "front", "edits": {"keystone": True}},
        ],
    }
