# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Pipelines registry loading and resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from remanence.core.errors import PipelineError, SchemaValidationError
from remanence.core.pipelines import build_registry, load_pipelines

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "pipelines.example.yaml"


def test_load_example_registry():
    registry = load_pipelines(EXAMPLE)
    assert [f.id for f in registry.formats()] == ["c64-5-25"]
    pipe = registry.get("fixture-c64")
    assert pipe.fixture is True
    assert pipe.output_format("flux") == "scp"
    assert registry.get("gw-c64-1541").requires_tools == ("gw",)


def test_pipelines_filtered_by_format():
    registry = load_pipelines(EXAMPLE)
    ids = {p.id for p in registry.pipelines("c64-5-25")}
    assert ids == {"gw-c64-1541", "fixture-c64"}
    assert registry.pipelines("nonexistent") == []


def test_unknown_pipeline_raises():
    registry = load_pipelines(EXAMPLE)
    with pytest.raises(PipelineError):
        registry.get("nope")


def test_dangling_format_reference_rejected():
    raw = {
        "schema_version": 1,
        "formats": [{"id": "fmt-a", "platform": "commodore-c64"}],
        "pipelines": [{
            "id": "p1", "format": "fmt-missing", "method": "greaseweazle",
            "preservation_level": "gold",
            "produces": [{"role": "flux", "format": "scp"}],
            "steps": [{"id": "s1", "action": "fixture", "asset": "x.scp", "produces": "flux"}],
        }],
    }
    with pytest.raises(PipelineError):
        build_registry(raw)


def test_invalid_registry_fails_schema():
    raw = {"schema_version": 1, "formats": [], "pipelines": []}  # minItems violated
    with pytest.raises(SchemaValidationError):
        build_registry(raw)
