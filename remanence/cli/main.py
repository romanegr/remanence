# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Command-line entry point: ``remanence`` (dump), ``--check``, ``--dry-run``.

The CLI only orchestrates :mod:`remanence.core`; it holds no business logic.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from ..core import preflight
from ..core.errors import RemanenceError
from ..core.pipelines import Pipeline, load_pipelines
from ..core.runner import Runner
from ..core.session import DumpSession
from ..core.staging import create_run

DEFAULT_PIPELINES = "pipelines.yaml"
DEFAULT_STAGING = "staging"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "check", False) or args.command == "check":
        return _cmd_check(args)
    if args.command == "dump":
        return _cmd_dump(args)
    if args.command == "gui":
        return _cmd_gui(args)

    parser.print_help()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="remanence", description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="validate pipelines.yaml and run the tooling preflight")
    parser.add_argument("--pipelines", default=DEFAULT_PIPELINES,
                        help="path to the pipelines registry (default: pipelines.yaml)")
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="validate config and tooling (F8)")
    p_check.add_argument("--pipelines", default=DEFAULT_PIPELINES)

    p_dump = sub.add_parser("dump", help="acquire a disk through a pipeline")
    p_dump.add_argument("--pipelines", default=DEFAULT_PIPELINES)
    p_dump.add_argument("--pipeline", required=True, help="pipeline id to run")
    p_dump.add_argument("--staging", default=DEFAULT_STAGING, help="staging root directory")
    p_dump.add_argument("--run-id", default=None)
    p_dump.add_argument("--device", default=None, help="device (e.g. /dev/ttyACM0)")
    p_dump.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                        help="pipeline parameter (repeatable)")
    p_dump.add_argument("--captured-by", default=os.environ.get("USER", "unknown"))
    p_dump.add_argument("--platform-hint", default=None)
    p_dump.add_argument("--dry-run", action="store_true",
                        help="resolve and print steps without executing or writing")

    p_gui = sub.add_parser("gui", help="launch the graphical interface")
    p_gui.add_argument("--pipelines", default=DEFAULT_PIPELINES)
    p_gui.add_argument("--staging", default=DEFAULT_STAGING)
    p_gui.add_argument("--catalog", default=None, help="catalogue root for Library mode")
    return parser


def _cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.pipelines)
    try:
        registry = load_pipelines(path)
    except (RemanenceError, OSError) as exc:
        print(f"FAIL  pipelines: {exc}", file=sys.stderr)
        return 1

    n_pipelines = len(registry.pipelines())
    print(f"OK    pipelines: {path} valid ({len(registry.formats())} formats, {n_pipelines} pipelines)")

    report = preflight.check_registry(registry)
    for name, status in sorted(report.tools.items()):
        mark = "OK   " if status.found else "MISS "
        version = f" ({status.version})" if status.version else ""
        where = status.path or "not found"
        print(f"{mark} tool {name}: {where}{version}")

    print("\nPipeline readiness:")
    for pipeline in registry.pipelines():
        ready = report.pipeline_ready[pipeline.id]
        print(f"  {'ready  ' if ready else 'blocked'}  {pipeline.id}")

    # Config validity is the gate; missing host tools are warnings, not failures.
    return 0


def _cmd_dump(args: argparse.Namespace) -> int:
    try:
        registry = load_pipelines(args.pipelines)
        pipeline = registry.get(args.pipeline)
    except (RemanenceError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    params = _parse_params(args.param, pipeline)

    if args.dry_run:
        run = create_run(args.staging, args.run_id)
        runner = Runner(run, log=print)
        runner.run_pipeline(pipeline, params, device=args.device, dry_run=True)
        print(f"\ndry-run: no files written (run dir {run.path} created empty)")
        return 0

    run = create_run(args.staging, args.run_id)
    runner = Runner(run, log=print)
    session = DumpSession(run, pipeline, captured_by=args.captured_by,
                          platform_hint=args.platform_hint)
    result = session.acquire(runner, params, device=args.device, best=True)

    if not result.produced:
        print("error: pipeline produced no files", file=sys.stderr)
        return 1

    verdict = session.assessment()
    print(f"disk assessed: {verdict.state} / {verdict.preservation_level} / {verdict.decode_status}")
    manifest_path = session.write_manifest()
    print(f"\nwrote {manifest_path}")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    try:
        from ..gui.app import run as run_gui  # lazy: PySide6 only needed for the GUI
    except ImportError as exc:
        print(f"error: GUI dependencies unavailable: {exc}", file=sys.stderr)
        return 1
    return run_gui(args.pipelines, args.staging, args.catalog)


def _parse_params(raw: list[str], pipeline: Pipeline) -> dict:
    declared = {p.name: p for p in pipeline.parameters}
    params: dict = {}
    for item in raw:
        if "=" not in item:
            raise SystemExit(f"invalid --param '{item}' (expected NAME=VALUE)")
        name, value = item.split("=", 1)
        param = declared.get(name)
        if param is not None and param.type == "int":
            params[name] = int(value)
        elif param is not None and param.type == "bool":
            params[name] = value.lower() in {"1", "true", "yes"}
        else:
            params[name] = value
    return params


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
