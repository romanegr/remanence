# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Pipelines registry: load, validate and resolve formats and pipelines.

The registry (``pipelines.yaml``) is validated against ``pipelines.schema.json``
and additionally cross-checked here for referential integrity (every pipeline
points at a declared format, identifiers are unique). See SOFTWARE-SPEC.md §F1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from . import schema
from .errors import PipelineError


@dataclass(frozen=True)
class Format:
    id: str
    platform: str
    media: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    default: Any = None
    description: str | None = None


@dataclass(frozen=True)
class Produces:
    role: str
    format: str
    optional: bool = False


@dataclass(frozen=True)
class Step:
    id: str
    action: str  # "command" | "fixture"
    description: str | None = None
    argv: tuple[str, ...] = ()
    asset: str | None = None
    produces: str | None = None
    allow_failure: bool = False
    unverified: bool = False


@dataclass(frozen=True)
class Pipeline:
    id: str
    format: str
    method: str
    preservation_level: str
    produces: tuple[Produces, ...]
    steps: tuple[Step, ...]
    hardware: str | None = None
    software: str | None = None
    fixture: bool = False
    requires_tools: tuple[str, ...] = ()
    parameters: tuple[Parameter, ...] = ()

    def output_format(self, role: str) -> str | None:
        for produced in self.produces:
            if produced.role == role:
                return produced.format
        return None


@dataclass(frozen=True)
class PipelineRegistry:
    _formats: dict[str, Format]
    _pipelines: dict[str, Pipeline]

    def formats(self) -> list[Format]:
        return list(self._formats.values())

    def get_format(self, format_id: str) -> Format:
        try:
            return self._formats[format_id]
        except KeyError as exc:
            raise PipelineError(f"unknown format: {format_id}") from exc

    def pipelines(self, format_id: str | None = None) -> list[Pipeline]:
        items = self._pipelines.values()
        if format_id is None:
            return list(items)
        return [p for p in items if p.format == format_id]

    def get(self, pipeline_id: str) -> Pipeline:
        try:
            return self._pipelines[pipeline_id]
        except KeyError as exc:
            raise PipelineError(f"unknown pipeline: {pipeline_id}") from exc


def load_pipelines(path: str | Path) -> PipelineRegistry:
    """Load, validate and resolve a pipelines registry from ``path``."""
    yaml = YAML(typ="safe")
    with open(path, "rb") as handle:
        raw = yaml.load(handle)
    if raw is None:
        raise PipelineError(f"empty pipelines file: {path}")
    return build_registry(raw)


def build_registry(raw: dict[str, Any]) -> PipelineRegistry:
    """Validate a raw registry mapping and build a :class:`PipelineRegistry`."""
    schema.validate(raw, "pipelines")

    formats: dict[str, Format] = {}
    for fmt in raw["formats"]:
        if fmt["id"] in formats:
            raise PipelineError(f"duplicate format id: {fmt['id']}")
        formats[fmt["id"]] = Format(
            id=fmt["id"],
            platform=fmt["platform"],
            media=fmt.get("media"),
            description=fmt.get("description"),
        )

    pipelines: dict[str, Pipeline] = {}
    for pipe in raw["pipelines"]:
        if pipe["id"] in pipelines:
            raise PipelineError(f"duplicate pipeline id: {pipe['id']}")
        if pipe["format"] not in formats:
            raise PipelineError(
                f"pipeline '{pipe['id']}' references unknown format '{pipe['format']}'"
            )
        pipelines[pipe["id"]] = _build_pipeline(pipe)

    return PipelineRegistry(_formats=formats, _pipelines=pipelines)


def _build_pipeline(pipe: dict[str, Any]) -> Pipeline:
    produces = tuple(
        Produces(role=p["role"], format=p["format"], optional=p.get("optional", False))
        for p in pipe["produces"]
    )
    parameters = tuple(
        Parameter(
            name=p["name"], type=p["type"],
            default=p.get("default"), description=p.get("description"),
        )
        for p in pipe.get("parameters", [])
    )
    steps = tuple(_build_step(s) for s in pipe["steps"])
    return Pipeline(
        id=pipe["id"],
        format=pipe["format"],
        method=pipe["method"],
        preservation_level=pipe["preservation_level"],
        produces=produces,
        steps=steps,
        hardware=pipe.get("hardware"),
        software=pipe.get("software"),
        fixture=pipe.get("fixture", False),
        requires_tools=tuple(pipe.get("requires", {}).get("tools", [])),
        parameters=parameters,
    )


def _build_step(step: dict[str, Any]) -> Step:
    return Step(
        id=step["id"],
        action=step["action"],
        description=step.get("description"),
        argv=tuple(step.get("argv", ())),
        asset=step.get("asset"),
        produces=step.get("produces"),
        allow_failure=step.get("allow_failure", False),
        unverified=step.get("unverified", False),
    )
