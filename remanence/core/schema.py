# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""JSON Schema loading and validation.

Schemas live in the top-level ``schemas/`` directory and are the single source
of truth for the on-disk YAML artefacts (CONVENTIONS.md §5). Every YAML write in
remanence is validated through :func:`validate` before it touches the disk.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import exceptions as js_exceptions

from .errors import SchemaValidationError

# schemas/ sits next to the importable package, at the repository root.
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

# Logical names mapped to their schema files.
SCHEMA_FILES = {
    "manifest": "manifest.schema.json",
    "item": "item.schema.json",
    "contents": "contents.schema.json",
    "disk": "disk.schema.json",
    "pipelines": "pipelines.schema.json",
}


def schema_path(name: str) -> Path:
    """Return the path of the schema file registered under ``name``."""
    try:
        return SCHEMA_DIR / SCHEMA_FILES[name]
    except KeyError as exc:
        raise SchemaValidationError(name, "unknown schema name") from exc


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Load and cache the JSON Schema registered under ``name``."""
    path = schema_path(name)
    try:
        with open(path, "rb") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SchemaValidationError(name, f"schema file not found: {path}") from exc


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(data: Any, schema_name: str) -> None:
    """Validate ``data`` against the named schema.

    Raises :class:`SchemaValidationError` with a readable, location-aware message
    on the first violation found.
    """
    validator = _validator(schema_name)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        raise SchemaValidationError(schema_name, _format_error(errors[0]))


def is_valid(data: Any, schema_name: str) -> bool:
    """Return whether ``data`` conforms to the named schema."""
    return _validator(schema_name).is_valid(data)


def _format_error(error: js_exceptions.ValidationError) -> str:
    location = "/".join(str(part) for part in error.absolute_path)
    where = f"at '{location}': " if location else ""
    return f"{where}{error.message}"
