# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Exception hierarchy for the core business logic."""

from __future__ import annotations


class RemanenceError(Exception):
    """Base class for every error raised by remanence core."""


class SchemaValidationError(RemanenceError):
    """A YAML/JSON document does not conform to its schema."""

    def __init__(self, schema_name: str, message: str) -> None:
        self.schema_name = schema_name
        super().__init__(f"[{schema_name}] {message}")


class PipelineError(RemanenceError):
    """A pipelines registry is invalid or a pipeline/format is missing."""


class PreflightError(RemanenceError):
    """A required external tool is missing or unusable."""


class RunnerError(RemanenceError):
    """A pipeline run could not be carried out."""


class StepFailed(RunnerError):
    """A pipeline step exited with a non-zero status (and was not allowed to fail)."""

    def __init__(self, step_id: str, returncode: int, message: str = "") -> None:
        self.step_id = step_id
        self.returncode = returncode
        detail = f": {message}" if message else ""
        super().__init__(f"step '{step_id}' failed (exit {returncode}){detail}")


class StagingError(RemanenceError):
    """An unsafe or impossible staging write was requested."""


class IntegrityError(RemanenceError):
    """A blob's sha256 does not match the catalogue metadata."""
