# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Canned fixture assets for the no-hardware pipeline (see SOFTWARE-SPEC.md §F7)."""

from importlib import resources
from pathlib import Path


def asset_path(name: str) -> Path:
    """Return the filesystem path of a bundled fixture asset."""
    return Path(resources.files(__package__) / "assets" / name)
