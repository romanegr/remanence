# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Flux variant management and disk-state assessment (SOFTWARE-SPEC.md §F3).

A disk may yield 0..N flux captures (variants) and 0..1 decoded image. This module
tracks the variants and derives the controlled-vocabulary fields the manifest
needs: ``decode_status``, ``needs_redecode``, ``preservation_level`` (CONVENTIONS.md
§3), plus a coarse visual state for the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .errors import RemanenceError

# Visual disk-state labels (UI indicator, SOFTWARE-SPEC.md §F3).
STATE_DECODED = "decoded"
STATE_FLUX_ONLY = "flux_only"
STATE_UNSTABLE = "unstable"
STATE_EMPTY = "empty"


@dataclass(frozen=True)
class FluxVariant:
    temp_name: str
    sha256: str
    variant: int
    best: bool = False
    read_quality: str | None = None
    captured_at: datetime | None = None


class FluxSet:
    """An ordered collection of flux variants for a single disk."""

    def __init__(self) -> None:
        self._variants: list[FluxVariant] = []

    def __len__(self) -> int:
        return len(self._variants)

    def __iter__(self):
        return iter(self._variants)

    @property
    def variants(self) -> list[FluxVariant]:
        return list(self._variants)

    def add(
        self,
        temp_name: str,
        sha256: str,
        *,
        read_quality: str | None = None,
        best: bool = False,
        captured_at: datetime | None = None,
    ) -> FluxVariant:
        """Append a new variant, assigning the next sequential variant number."""
        variant = FluxVariant(
            temp_name=temp_name,
            sha256=sha256,
            variant=len(self._variants) + 1,
            best=best,
            read_quality=read_quality,
            captured_at=captured_at or datetime.now(timezone.utc),
        )
        self._variants.append(variant)
        if best:
            self.mark_best(variant.variant)
        return variant

    def mark_best(self, variant: int) -> None:
        """Mark one variant as the best read; clears the flag on all others."""
        if not any(v.variant == variant for v in self._variants):
            raise RemanenceError(f"no such flux variant: {variant}")
        self._variants = [
            FluxVariant(**{**v.__dict__, "best": v.variant == variant})
            for v in self._variants
        ]

    def remove(self, variant: int) -> None:
        """Remove a variant (does not renumber the survivors)."""
        before = len(self._variants)
        self._variants = [v for v in self._variants if v.variant != variant]
        if len(self._variants) == before:
            raise RemanenceError(f"no such flux variant: {variant}")

    def best(self) -> FluxVariant | None:
        for v in self._variants:
            if v.best:
                return v
        return None


@dataclass(frozen=True)
class DiskAssessment:
    decode_status: str          # ok | failed | not_attempted
    preservation_level: str     # gold | silver | bronze
    needs_redecode: bool
    state: str                  # decoded | flux_only | unstable | empty


def assess_disk(
    *,
    has_flux: bool,
    has_image: bool,
    decode_attempted: bool,
    decode_succeeded: bool,
    capture_partial: bool = False,
    flux_stable: bool = True,
) -> DiskAssessment:
    """Derive decode status and preservation level from the acquisition outcome.

    Mapping (CONVENTIONS.md §3):

    * ``gold``   — flux present and a verified decoded image (decode succeeded);
    * ``silver`` — flux kept without a verified decode;
    * ``bronze`` — image only, or any partial capture.
    """
    if not has_flux and not has_image:
        return DiskAssessment("not_attempted", "bronze", needs_redecode=False, state=STATE_EMPTY)

    if decode_succeeded:
        decode_status = "ok"
    elif decode_attempted:
        decode_status = "failed"
    else:
        decode_status = "not_attempted"

    # A kept-but-undecoded flux is the redecode candidate (F3 deferred decode).
    needs_redecode = has_flux and not decode_succeeded

    if capture_partial:
        preservation_level = "bronze"
    elif has_flux and decode_succeeded and has_image:
        preservation_level = "gold"
    elif has_flux:
        preservation_level = "silver"
    else:  # image only, no flux
        preservation_level = "bronze"

    if has_image and decode_succeeded:
        state = STATE_DECODED
    elif has_flux and not flux_stable:
        state = STATE_UNSTABLE
    else:
        state = STATE_FLUX_ONLY

    return DiskAssessment(decode_status, preservation_level, needs_redecode, state)
