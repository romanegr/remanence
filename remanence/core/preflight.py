# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Preflight: detect external tools required by pipelines (SOFTWARE-SPEC.md §F1, §F8).

Greaseweazle ships inside the venv; the remaining tools (OpenCBM, VICE, mtools,
AppleCommander, ADTPro) are host binaries checked here. Detection uses
``shutil.which``; version probing is best-effort and never fatal.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

from .pipelines import Pipeline, PipelineRegistry

# Best-effort version flags per known tool. Unknown tools are detected by path only.
_VERSION_FLAGS = {
    "gw": ["--version"],
    "cbmctrl": ["--version"],
    "d64copy": ["--version"],
    "c1541": ["-h"],
    "petcat": ["-h"],
    "mdir": ["--version"],
}


@dataclass(frozen=True)
class ToolStatus:
    name: str
    found: bool
    path: str | None = None
    version: str | None = None


@dataclass
class PreflightReport:
    tools: dict[str, ToolStatus] = field(default_factory=dict)
    pipeline_ready: dict[str, bool] = field(default_factory=dict)

    @property
    def all_tools_present(self) -> bool:
        return all(status.found for status in self.tools.values())

    def missing_tools(self) -> list[str]:
        return [name for name, status in self.tools.items() if not status.found]


def check_tool(name: str, *, probe_version: bool = True) -> ToolStatus:
    """Detect a single tool by name."""
    path = shutil.which(name)
    if path is None:
        return ToolStatus(name=name, found=False)
    version = _probe_version(name, path) if probe_version else None
    return ToolStatus(name=name, found=True, path=path, version=version)


def check_tools(names: list[str], *, probe_version: bool = True) -> list[ToolStatus]:
    """Detect a list of tools, preserving order and de-duplicating."""
    seen: dict[str, ToolStatus] = {}
    for name in names:
        if name not in seen:
            seen[name] = check_tool(name, probe_version=probe_version)
    return list(seen.values())


def check_pipeline(pipeline: Pipeline, *, probe_version: bool = True) -> list[ToolStatus]:
    """Detect the tools a single pipeline requires."""
    return check_tools(list(pipeline.requires_tools), probe_version=probe_version)


def check_registry(registry: PipelineRegistry, *, probe_version: bool = True) -> PreflightReport:
    """Detect every tool used across the registry and report per-pipeline readiness."""
    report = PreflightReport()
    all_names: list[str] = []
    for pipeline in registry.pipelines():
        all_names.extend(pipeline.requires_tools)
    for status in check_tools(all_names, probe_version=probe_version):
        report.tools[status.name] = status
    for pipeline in registry.pipelines():
        report.pipeline_ready[pipeline.id] = all(
            report.tools[name].found for name in pipeline.requires_tools
        )
    return report


def _probe_version(name: str, path: str) -> str | None:
    flags = _VERSION_FLAGS.get(name)
    if flags is None:
        return None
    try:
        result = subprocess.run(
            [path, *flags],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stdout or result.stderr or "").strip()
    return output.splitlines()[0] if output else None
