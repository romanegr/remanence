# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Pipeline runner: execute steps, substitute variables, capture logs.

A single :meth:`Runner.run_pipeline` call performs one acquisition pass and
returns the files it produced. Calling it again on the same run adds a *new*
flux variant (the "re-read" of SOFTWARE-SPEC.md §F3), since each call allocates
fresh temporary output names.

Two step actions are supported:

* ``command`` — run an external program (``argv``). Steps flagged ``unverified``
  are real hardware skeletons "to be confirmed"; remanence never claims to have
  executed them.
* ``fixture`` — copy a bundled canned asset to the produced output, so the whole
  chain (F2→F6) runs with no drive and no disk (SOFTWARE-SPEC.md §F7).

Variable substitution understands ``${device}``, ``${run_dir}``,
``${param.<name>}`` and ``${out.<role>}``.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..fixtures import asset_path
from .errors import RunnerError, StepFailed
from .pipelines import Pipeline, Step
from .staging import StagingRun

LogCallback = Callable[[str], None]

_VAR_RE = re.compile(r"\$\{([a-z_]+(?:\.[a-z0-9_]+)?)\}")

# Default output extension when a role is not declared in pipeline.produces.
_DEFAULT_EXT = "bin"


@dataclass(frozen=True)
class ProducedFile:
    role: str
    temp_name: str
    path: Path
    format: str


@dataclass
class StepResult:
    step_id: str
    status: str  # "ok" | "failed" | "skipped"
    returncode: int | None = None
    log: str = ""


@dataclass
class RunResult:
    pipeline_id: str
    success: bool
    produced: dict[str, ProducedFile] = field(default_factory=dict)
    steps: list[StepResult] = field(default_factory=list)
    failed_optional: list[str] = field(default_factory=list)


class Runner:
    """Execute a pipeline against a staging run."""

    def __init__(self, run: StagingRun, log: LogCallback | None = None) -> None:
        self.run = run
        self._log = log or (lambda _msg: None)

    def run_pipeline(
        self,
        pipeline: Pipeline,
        params: dict[str, Any] | None = None,
        *,
        device: str | None = None,
        dry_run: bool = False,
    ) -> RunResult:
        params = self._resolve_params(pipeline, params or {})
        outputs = self._allocate_outputs(pipeline)
        context = self._build_context(pipeline, params, device, outputs)

        result = RunResult(pipeline_id=pipeline.id, success=True)
        for step in pipeline.steps:
            step_result = self._run_step(step, context, dry_run=dry_run)
            result.steps.append(step_result)
            if step_result.status == "failed":
                if step.allow_failure:
                    if step.produces:
                        result.failed_optional.append(step.produces)
                    continue
                result.success = False
                break

        if not dry_run:
            self._collect_produced(pipeline, outputs, result)
        return result

    # -- internals --------------------------------------------------------

    def _resolve_params(self, pipeline: Pipeline, given: dict[str, Any]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        declared = {p.name: p for p in pipeline.parameters}
        for name, param in declared.items():
            resolved[name] = given.get(name, param.default)
        unknown = set(given) - set(declared)
        if unknown:
            raise RunnerError(f"unknown parameter(s) for '{pipeline.id}': {sorted(unknown)}")
        return resolved

    def _allocate_outputs(self, pipeline: Pipeline) -> dict[str, ProducedFile]:
        outputs: dict[str, ProducedFile] = {}
        for produced in pipeline.produces:
            temp_name = self.run.alloc_temp(produced.role, produced.format)
            outputs[produced.role] = ProducedFile(
                role=produced.role,
                temp_name=temp_name,
                path=self.run.path / temp_name,
                format=produced.format,
            )
        return outputs

    def _build_context(
        self,
        pipeline: Pipeline,
        params: dict[str, Any],
        device: str | None,
        outputs: dict[str, ProducedFile],
    ) -> dict[str, str]:
        context: dict[str, str] = {"run_dir": str(self.run.path)}
        if device is not None:
            context["device"] = device
        for name, value in params.items():
            context[f"param.{name}"] = "" if value is None else str(value)
        for role, produced in outputs.items():
            context[f"out.{role}"] = str(produced.path)
        return context

    def _substitute(self, token: str, context: dict[str, str], step: Step) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in context:
                raise RunnerError(
                    f"step '{step.id}': unknown variable '${{{key}}}'"
                )
            return context[key]

        return _VAR_RE.sub(replace, token)

    def _run_step(self, step: Step, context: dict[str, str], *, dry_run: bool) -> StepResult:
        if step.unverified:
            self._log(f"[{step.id}] HARDWARE STEP (to be confirmed, not executed by remanence)")
        if step.action == "command":
            return self._run_command(step, context, dry_run=dry_run)
        if step.action == "fixture":
            return self._run_fixture(step, context, dry_run=dry_run)
        raise RunnerError(f"step '{step.id}': unknown action '{step.action}'")

    def _run_command(self, step: Step, context: dict[str, str], *, dry_run: bool) -> StepResult:
        argv = [self._substitute(tok, context, step) for tok in step.argv]
        self._log(f"[{step.id}] $ {' '.join(argv)}")
        if dry_run or step.unverified:
            # Never execute hardware skeletons; dry-run only resolves the command.
            return StepResult(step.id, status="skipped")
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise StepFailed(step.id, -1, str(exc)) from exc
        log = (proc.stdout or "") + (proc.stderr or "")
        if log:
            self._log(log.rstrip())
        if proc.returncode != 0:
            return StepResult(step.id, status="failed", returncode=proc.returncode, log=log)
        return StepResult(step.id, status="ok", returncode=0, log=log)

    def _run_fixture(self, step: Step, context: dict[str, str], *, dry_run: bool) -> StepResult:
        if step.produces is None or step.asset is None:
            raise RunnerError(f"fixture step '{step.id}' needs both 'asset' and 'produces'")
        dest_key = f"out.{step.produces}"
        if dest_key not in context:
            raise RunnerError(f"fixture step '{step.id}' produces undeclared role '{step.produces}'")
        dest = Path(context[dest_key])
        self._log(f"[{step.id}] fixture: {step.asset} -> {dest.name}")
        if dry_run:
            return StepResult(step.id, status="skipped")
        src = asset_path(step.asset)
        if not src.is_file():
            return StepResult(step.id, status="failed", log=f"missing fixture asset: {step.asset}")
        self.run.add_file(src, dest.name, overwrite=True)
        return StepResult(step.id, status="ok", returncode=0)

    def _collect_produced(
        self,
        pipeline: Pipeline,
        outputs: dict[str, ProducedFile],
        result: RunResult,
    ) -> None:
        for role, produced in outputs.items():
            if produced.path.is_file():
                result.produced[role] = produced
