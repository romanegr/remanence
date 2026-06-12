# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Core business logic for remanence (no GUI, no hardware required)."""

from __future__ import annotations

from .errors import (
    IntegrityError,
    PipelineError,
    PreflightError,
    RemanenceError,
    RunnerError,
    SchemaValidationError,
    StagingError,
    StepFailed,
)
from .hashing import sha256_bytes, sha256_file
from .schema import is_valid, load_schema, validate

__all__ = [
    "RemanenceError",
    "SchemaValidationError",
    "PipelineError",
    "PreflightError",
    "RunnerError",
    "StepFailed",
    "StagingError",
    "IntegrityError",
    "sha256_bytes",
    "sha256_file",
    "load_schema",
    "validate",
    "is_valid",
]
