# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Runner tests: fixture chain, variable substitution, dry-run, allow_failure."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from remanence.core.errors import RunnerError
from remanence.core.manifest import ManifestBuilder
from remanence.core.pipelines import (
    Pipeline,
    Produces,
    Step,
    load_pipelines,
)
from remanence.core.runner import Runner
from remanence.core.staging import create_run

EXAMPLE = Path(__file__).resolve().parents[1] / "pipelines.example.yaml"


def test_fixture_pipeline_produces_flux_and_image(tmp_path):
    registry = load_pipelines(EXAMPLE)
    pipeline = registry.get("fixture-c64")
    run = create_run(tmp_path, "run01")
    logs: list[str] = []
    runner = Runner(run, log=logs.append)

    result = runner.run_pipeline(pipeline, {})
    assert result.success is True
    assert set(result.produced) == {"flux", "image"}
    assert result.produced["flux"].path.read_bytes()[:3] == b"SCP"
    assert result.produced["image"].path.stat().st_size == 174848
    assert any("fixture" in line for line in logs)


def test_full_fixture_chain_to_manifest(tmp_path):
    """F2 to F6 with no hardware: run -> manifest with sha256, schema-valid."""
    registry = load_pipelines(EXAMPLE)
    pipeline = registry.get("fixture-c64")
    run = create_run(tmp_path, "run01")
    runner = Runner(run)
    result = runner.run_pipeline(pipeline, {})

    builder = ManifestBuilder(
        run,
        pipeline_id=pipeline.id,
        captured_by="operator-id",
        method=pipeline.method,
        preservation_level=pipeline.preservation_level,
        platform_hint="commodore-c64",
    ).set_decode_status("ok", needs_redecode=False, flux_stable=True)
    builder.add_flux_variant(result.produced["flux"].temp_name, variant=1, best=True,
                             read_quality="clean")
    builder.set_image(result.produced["image"].temp_name, fmt="d64")
    manifest = builder.build()
    assert manifest["files"][0]["sha256"]
    path = builder.write()
    assert path.name == "manifest.yaml"


def test_reread_creates_distinct_variants(tmp_path):
    """Calling run twice yields distinct flux temp names (F3 re-read)."""
    registry = load_pipelines(EXAMPLE)
    pipeline = registry.get("fixture-c64")
    run = create_run(tmp_path, "run01")
    runner = Runner(run)
    first = runner.run_pipeline(pipeline, {})
    second = runner.run_pipeline(pipeline, {})
    assert first.produced["flux"].temp_name != second.produced["flux"].temp_name
    assert first.produced["flux"].temp_name == "flux_read01.scp"
    assert second.produced["flux"].temp_name == "flux_read02.scp"


def test_dry_run_executes_nothing(tmp_path):
    registry = load_pipelines(EXAMPLE)
    pipeline = registry.get("fixture-c64")
    run = create_run(tmp_path, "run01")
    runner = Runner(run)
    result = runner.run_pipeline(pipeline, {}, dry_run=True)
    assert all(s.status == "skipped" for s in result.steps)
    assert result.produced == {}


def test_unknown_parameter_rejected(tmp_path):
    registry = load_pipelines(EXAMPLE)
    pipeline = registry.get("fixture-c64")
    run = create_run(tmp_path, "run01")
    runner = Runner(run)
    with pytest.raises(RunnerError):
        runner.run_pipeline(pipeline, {"nope": 1})


def test_hardware_command_steps_are_not_executed(tmp_path):
    """Unverified hardware steps are resolved and logged but never run."""
    registry = load_pipelines(EXAMPLE)
    pipeline = registry.get("gw-c64-1541")
    run = create_run(tmp_path, "run01")
    logs: list[str] = []
    runner = Runner(run, log=logs.append)
    result = runner.run_pipeline(pipeline, {"revolutions": 5, "tracks": "0-39"}, device="/dev/ttyACM0")
    assert all(s.status == "skipped" for s in result.steps)
    # The resolved command shows substituted variables.
    assert any("/dev/ttyACM0" in line for line in logs)
    assert any("to be confirmed" in line for line in logs)


def _python_step(code: str, *, allow_failure: bool, produces: str | None = None) -> Step:
    return Step(
        id="py", action="command",
        argv=(sys.executable, "-c", code),
        produces=produces, allow_failure=allow_failure,
    )


def test_allow_failure_continues_and_marks_optional(tmp_path):
    run = create_run(tmp_path, "run01")
    pipeline = Pipeline(
        id="t", format="f", method="greaseweazle", preservation_level="silver",
        produces=(Produces("flux", "scp"), Produces("image", "d64", optional=True)),
        steps=(
            _python_step("open(r'%s','wb').write(b'x')" % (run.path / "flux_read01.scp"),
                         allow_failure=False, produces="flux"),
            _python_step("import sys; sys.exit(3)", allow_failure=True, produces="image"),
        ),
    )
    runner = Runner(run)
    result = runner.run_pipeline(pipeline, {})
    assert result.success is True
    assert "image" in result.failed_optional
    assert result.steps[1].status == "failed"


def test_required_step_failure_stops_run(tmp_path):
    run = create_run(tmp_path, "run01")
    pipeline = Pipeline(
        id="t", format="f", method="greaseweazle", preservation_level="bronze",
        produces=(Produces("flux", "scp"),),
        steps=(_python_step("import sys; sys.exit(1)", allow_failure=False, produces="flux"),),
    )
    runner = Runner(run)
    result = runner.run_pipeline(pipeline, {})
    assert result.success is False
