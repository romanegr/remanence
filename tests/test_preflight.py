# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Preflight tool-detection tests (no hardware)."""

from __future__ import annotations

from pathlib import Path

from remanence.core import preflight
from remanence.core.pipelines import load_pipelines

EXAMPLE = Path(__file__).resolve().parents[1] / "pipelines.example.yaml"


def test_check_existing_tool():
    # 'sh' is present on any Linux host.
    status = preflight.check_tool("sh", probe_version=False)
    assert status.found is True
    assert status.path is not None


def test_check_missing_tool():
    status = preflight.check_tool("definitely-not-a-real-tool-xyz", probe_version=False)
    assert status.found is False
    assert status.path is None


def test_check_tools_deduplicates():
    statuses = preflight.check_tools(["sh", "sh"], probe_version=False)
    assert len(statuses) == 1


def test_check_registry_reports_pipeline_readiness():
    registry = load_pipelines(EXAMPLE)
    report = preflight.check_registry(registry, probe_version=False)
    # The fixture pipeline requires no tools, so it is always ready.
    assert report.pipeline_ready["fixture-c64"] is True
    # gw-c64-1541 readiness depends on whether 'gw' is installed.
    assert "gw" in report.tools
    assert report.pipeline_ready["gw-c64-1541"] == report.tools["gw"].found
