# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Dump session orchestration (SOFTWARE-SPEC.md §8 wizard).

A :class:`DumpSession` sequences the core modules (runner, flux, images, manifest,
staging) for a single disk: acquire one or more flux variants, register the
optional decoded image, attach photos and metadata, then assess the disk and
write the manifest. Both the CLI and the GUI drive this object, so neither holds
any business logic. Fully testable without GUI or hardware.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import images
from .flux import DiskAssessment, FluxSet, assess_disk
from .hashing import sha256_file
from .images import EditOps
from .manifest import ManifestBuilder, load_manifest
from .pipelines import Pipeline, PipelineRegistry
from .runner import RunResult, Runner
from .staging import StagingRun, reopen_run


class DumpSession:
    """Stateful orchestration of one disk acquisition."""

    def __init__(
        self,
        run: StagingRun,
        pipeline: Pipeline,
        *,
        captured_by: str,
        platform_hint: str | None = None,
    ) -> None:
        self.run = run
        self.pipeline = pipeline
        self.captured_by = captured_by
        self.platform_hint = platform_hint

        self.flux = FluxSet()
        self.image_temp_name: str | None = None
        self.image_format: str | None = None
        self.flux_stable: bool = True
        self.capture_partial: bool = False
        self._photos: list[dict[str, Any]] = []
        self._physical: dict[str, Any] = {}
        self.label_text_file: str | None = None
        self.listing_file: str | None = None

        self._decode_offered = any(p.role == "image" for p in pipeline.produces)

    # -- acquisition ------------------------------------------------------

    def acquire(
        self,
        runner: Runner,
        params: dict[str, Any] | None = None,
        *,
        device: str | None = None,
        best: bool = False,
        read_quality: str | None = None,
    ) -> RunResult:
        """Run one acquisition pass; register its flux variant and image.

        Calling this again performs a "re-read", adding another flux variant
        (SOFTWARE-SPEC.md §F3).
        """
        result = runner.run_pipeline(self.pipeline, params or {}, device=device)
        if "flux" in result.produced:
            produced = result.produced["flux"]
            self.flux.add(
                produced.temp_name,
                sha256_file(produced.path),
                read_quality=read_quality,
                best=best,
            )
        if "image" in result.produced:
            produced = result.produced["image"]
            self.image_temp_name = produced.temp_name
            self.image_format = produced.format
        return result

    def mark_best(self, variant: int) -> None:
        self.flux.mark_best(variant)

    def remove_variant(self, variant: int) -> None:
        self.flux.remove(variant)

    def discard_image(self) -> None:
        """Keep the flux only (defective/undecodable disk, F3)."""
        self.image_temp_name = None
        self.image_format = None

    # -- photos and metadata ---------------------------------------------

    def add_photo(
        self,
        source: str | Path,
        *,
        type: str,
        ops: EditOps | None = None,
        disk_id: str | None = None,
        note: str | None = None,
        order: int | None = None,
    ) -> str:
        """Normalise a photo into the run and record its manifest entry.

        Returns the run-relative path of the exported JPEG.
        """
        ops = ops or EditOps()
        rel = self._photo_name(type, disk_id)
        dest = self.run.photos_dir / Path(rel).name
        images.export_normalized(source, ops, dest)
        entry: dict[str, Any] = {"file": rel, "type": type}
        if disk_id is not None:
            entry["disk_id"] = disk_id
        if note is not None:
            entry["note"] = note
        if order is not None:
            entry["order"] = order
        edits = ops.to_dict()
        if edits:
            entry["edits"] = edits
        self._photos.append(entry)
        return rel

    def set_label_text(self, text: str) -> None:
        self.run.write_atomic("label.txt", text, overwrite=True)
        self.label_text_file = "label.txt"

    def set_physical(self, **fields: Any) -> None:
        self._physical = {k: v for k, v in fields.items() if v is not None}

    # -- assessment and manifest -----------------------------------------

    def assessment(self) -> DiskAssessment:
        return assess_disk(
            has_flux=len(self.flux) > 0,
            has_image=self.image_temp_name is not None,
            decode_attempted=self._decode_offered,
            decode_succeeded=self.image_temp_name is not None,
            capture_partial=self.capture_partial,
            flux_stable=self.flux_stable,
        )

    def build_manifest(self) -> ManifestBuilder:
        verdict = self.assessment()
        builder = ManifestBuilder(
            self.run,
            pipeline_id=self.pipeline.id,
            captured_by=self.captured_by,
            method=self.pipeline.method,
            preservation_level=verdict.preservation_level,
            platform_hint=self.platform_hint,
            hardware=self.pipeline.hardware,
            software=self.pipeline.software,
        ).set_decode_status(
            verdict.decode_status,
            needs_redecode=verdict.needs_redecode,
            flux_stable=self.flux_stable,
        )
        if self._physical:
            builder.set_physical(**self._physical)
        builder.set_label_text_file(self.label_text_file)
        builder.set_listing_file(self.listing_file)
        for variant in self.flux:
            builder.add_flux_variant(
                variant.temp_name,
                variant=variant.variant,
                best=variant.best,
                read_quality=variant.read_quality,
            )
        if self.image_temp_name is not None:
            builder.set_image(self.image_temp_name, fmt=self.image_format or "img")
        for photo in self._photos:
            builder.add_photo(
                photo["file"],
                type=photo["type"],
                disk_id=photo.get("disk_id"),
                note=photo.get("note"),
                order=photo.get("order"),
                edits=photo.get("edits"),
            )
        return builder

    def write_manifest(self) -> Path:
        return self.build_manifest().write()

    # -- internals --------------------------------------------------------

    def _photo_name(self, type: str, disk_id: str | None) -> str:
        stem = f"{disk_id}-{type}" if disk_id else type
        existing = {p["file"] for p in self._photos}
        candidate = f"photos/{stem}.jpg"
        n = 2
        while candidate in existing:
            candidate = f"photos/{stem}-{n}.jpg"
            n += 1
        return candidate


def load_session(run_path: str | Path, registry: PipelineRegistry) -> DumpSession:
    """Reopen an existing run and reconstruct its session (SOFTWARE-SPEC.md §F9).

    Reads ``manifest.yaml`` from the run, resolves its pipeline from ``registry``
    and restores flux variants, the optional image, metadata and photos so the
    operator can add photos or amend metadata without re-running the dump.
    """
    run = reopen_run(run_path)
    manifest = load_manifest(run.manifest_path)
    pipeline = registry.get(manifest["pipeline_id"])

    session = DumpSession(
        run,
        pipeline,
        captured_by=manifest["captured_by"],
        platform_hint=manifest.get("platform_hint"),
    )
    session.flux_stable = manifest.get("flux_stable", True)
    for entry in manifest["files"]:
        if entry["role"] == "flux":
            session.flux.add(
                entry["temp_name"],
                entry["sha256"],
                read_quality=entry.get("read_quality"),
                best=entry.get("best", False),
            )
        elif entry["role"] == "image":
            session.image_temp_name = entry["temp_name"]
            session.image_format = entry["format"]
    if "physical" in manifest:
        session._physical = dict(manifest["physical"])
    session.label_text_file = manifest.get("label_text_file")
    session.listing_file = manifest.get("listing_file")
    session._photos = [dict(p) for p in manifest.get("photos", [])]
    return session
