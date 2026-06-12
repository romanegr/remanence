# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Manifest construction and writing (SOFTWARE-SPEC.md §F6, CONVENTIONS.md §5).

The :class:`ManifestBuilder` accumulates acquisition context, flux variants, the
optional decoded image, photos and metadata, then computes the ``sha256`` of every
produced file and writes a schema-validated ``manifest.yaml`` atomically.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from . import schema
from .errors import StagingError
from .hashing import sha256_file
from .staging import StagingRun

SCHEMA_VERSION = 1


def _yaml() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    return y


class ManifestBuilder:
    """Build and write a run manifest.

    File entries reference run-relative ``temp_name`` paths; their ``sha256`` is
    computed from the on-disk files at :meth:`build` time, so the manifest always
    reflects what was actually written.
    """

    def __init__(
        self,
        run: StagingRun,
        *,
        pipeline_id: str,
        captured_by: str,
        method: str,
        preservation_level: str,
        platform_hint: str | None = None,
        hardware: str | None = None,
        software: str | None = None,
        revolutions: int | None = None,
        date_captured: datetime | None = None,
    ) -> None:
        self.run = run
        self.pipeline_id = pipeline_id
        self.captured_by = captured_by
        self.platform_hint = platform_hint
        self.date_captured = date_captured or datetime.now(timezone.utc)
        self._acquisition: dict[str, Any] = {"method": method, "preservation_level": preservation_level}
        if hardware is not None:
            self._acquisition["hardware"] = hardware
        if software is not None:
            self._acquisition["software"] = software
        if revolutions is not None:
            self._acquisition["revolutions"] = revolutions

        self.decode_status: str = "not_attempted"
        self.needs_redecode: bool | None = None
        self.flux_stable: bool | None = None
        self._physical: dict[str, Any] | None = None
        self.label_text_file: str | None = None
        self.listing_file: str | None = None
        self._files: list[dict[str, Any]] = []
        self._photos: list[dict[str, Any]] = []

    # -- acquisition outcome ---------------------------------------------

    def set_decode_status(
        self,
        status: str,
        *,
        needs_redecode: bool | None = None,
        flux_stable: bool | None = None,
    ) -> "ManifestBuilder":
        self.decode_status = status
        if needs_redecode is not None:
            self.needs_redecode = needs_redecode
        if flux_stable is not None:
            self.flux_stable = flux_stable
        return self

    def set_physical(
        self,
        *,
        media: str | None = None,
        sides: int | None = None,
        write_protected: bool | None = None,
        condition: str | None = None,
    ) -> "ManifestBuilder":
        physical: dict[str, Any] = {}
        if media is not None:
            physical["media"] = media
        if sides is not None:
            physical["sides"] = sides
        if write_protected is not None:
            physical["write_protected"] = write_protected
        if condition is not None:
            physical["condition"] = condition
        self._physical = physical
        return self

    def set_label_text_file(self, rel: str | None) -> "ManifestBuilder":
        self.label_text_file = rel
        return self

    def set_listing_file(self, rel: str | None) -> "ManifestBuilder":
        self.listing_file = rel
        return self

    # -- files ------------------------------------------------------------

    def add_flux_variant(
        self,
        temp_name: str,
        *,
        variant: int,
        best: bool = False,
        read_quality: str | None = None,
        fmt: str = "scp",
        upload: bool = True,
    ) -> "ManifestBuilder":
        entry: dict[str, Any] = {
            "temp_name": temp_name,
            "role": "flux",
            "format": fmt,
            "variant": variant,
            "best": best,
            "upload": upload,
            "tosec_name": None,
        }
        if read_quality is not None:
            entry["read_quality"] = read_quality
        self._files.append(entry)
        return self

    def set_image(self, temp_name: str, *, fmt: str, upload: bool = True) -> "ManifestBuilder":
        self._files.append(
            {"temp_name": temp_name, "role": "image", "format": fmt,
             "upload": upload, "tosec_name": None}
        )
        return self

    def add_file(
        self,
        temp_name: str,
        *,
        role: str,
        fmt: str,
        upload: bool = True,
    ) -> "ManifestBuilder":
        self._files.append(
            {"temp_name": temp_name, "role": role, "format": fmt,
             "upload": upload, "tosec_name": None}
        )
        return self

    # -- photos -----------------------------------------------------------

    def add_photo(
        self,
        file: str,
        *,
        type: str,
        disk_id: str | None = None,
        note: str | None = None,
        order: int | None = None,
        edits: dict[str, Any] | None = None,
    ) -> "ManifestBuilder":
        entry: dict[str, Any] = {"file": file, "type": type}
        if disk_id is not None:
            entry["disk_id"] = disk_id
        if note is not None:
            entry["note"] = note
        if order is not None:
            entry["order"] = order
        if edits is not None:
            entry["edits"] = edits
        self._photos.append(entry)
        return self

    # -- build / write ----------------------------------------------------

    def build(self) -> dict[str, Any]:
        """Assemble, hash every file and validate the manifest dictionary."""
        if not self._files:
            raise StagingError("manifest must reference at least one flux or image file")
        roles = {f["role"] for f in self._files}
        if not (roles & {"flux", "image"}):
            raise StagingError("manifest must contain at least one flux or image (SOFTWARE-SPEC §F6)")

        files = []
        for entry in self._files:
            full = self.run.path / entry["temp_name"]
            if not full.is_file():
                raise StagingError(f"referenced file is missing from the run: {entry['temp_name']}")
            files.append({**entry, "sha256": sha256_file(full)})

        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run.run_id,
            "pipeline_id": self.pipeline_id,
            "captured_by": self.captured_by,
            "date_captured": self.date_captured.isoformat(),
            "acquisition": self._acquisition,
            "decode_status": self.decode_status,
            "files": files,
        }
        if self.platform_hint is not None:
            manifest["platform_hint"] = self.platform_hint
        if self.needs_redecode is not None:
            manifest["needs_redecode"] = self.needs_redecode
        if self.flux_stable is not None:
            manifest["flux_stable"] = self.flux_stable
        if self._physical is not None:
            manifest["physical"] = self._physical
        manifest["label_text_file"] = self.label_text_file
        manifest["listing_file"] = self.listing_file
        if self._photos:
            manifest["photos"] = self._photos

        schema.validate(manifest, "manifest")
        return manifest

    def write(self) -> Path:
        """Build, validate and atomically write ``manifest.yaml`` into the run."""
        manifest = self.build()
        buffer = io.StringIO()
        _yaml().dump(manifest, buffer)
        self.run.write_atomic(self.run.manifest_path.name, buffer.getvalue(), overwrite=True)
        return self.run.manifest_path


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load and validate a manifest from disk."""
    with open(path, "rb") as handle:
        data = _yaml().load(handle)
    plain = _to_plain(data)
    schema.validate(plain, "manifest")
    return plain


def _to_plain(data: Any) -> Any:
    """Recursively convert ruamel structures to plain dict/list for validation."""
    if isinstance(data, dict):
        return {str(k): _to_plain(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_to_plain(v) for v in data]
    return data
