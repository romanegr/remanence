# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""CLI tests: --check, dump (fixture), dry-run."""

from __future__ import annotations

from pathlib import Path

from remanence.cli.main import main
from remanence.core.manifest import load_manifest

EXAMPLE = str(Path(__file__).resolve().parents[1] / "pipelines.example.yaml")


def test_check_valid_registry(capsys):
    rc = main(["--check", "--pipelines", EXAMPLE])
    out = capsys.readouterr().out
    assert rc == 0
    assert "valid" in out
    assert "fixture-c64" in out


def test_check_subcommand(capsys):
    rc = main(["check", "--pipelines", EXAMPLE])
    assert rc == 0
    assert "Pipeline readiness" in capsys.readouterr().out


def test_check_invalid_path():
    rc = main(["--check", "--pipelines", "/nonexistent/pipelines.yaml"])
    assert rc == 1


def test_dump_fixture_produces_staging(tmp_path, capsys):
    rc = main([
        "dump", "--pipelines", EXAMPLE, "--pipeline", "fixture-c64",
        "--staging", str(tmp_path), "--run-id", "run01",
        "--captured-by", "tester", "--platform-hint", "commodore-c64",
    ])
    assert rc == 0
    manifest_path = tmp_path / "run01" / "manifest.yaml"
    assert manifest_path.exists()
    manifest = load_manifest(manifest_path)
    assert manifest["pipeline_id"] == "fixture-c64"
    assert manifest["acquisition"]["preservation_level"] == "gold"
    roles = {f["role"] for f in manifest["files"]}
    assert roles == {"flux", "image"}
    # Every produced file carries a sha256.
    assert all(f["sha256"] for f in manifest["files"])


def test_dump_dry_run_writes_nothing(tmp_path, capsys):
    rc = main([
        "dump", "--pipelines", EXAMPLE, "--pipeline", "fixture-c64",
        "--staging", str(tmp_path), "--run-id", "run01", "--dry-run",
    ])
    assert rc == 0
    assert not (tmp_path / "run01" / "manifest.yaml").exists()
    assert "dry-run" in capsys.readouterr().out


def test_no_args_prints_help(capsys):
    rc = main([])
    assert rc == 0
    assert "usage" in capsys.readouterr().out.lower()
