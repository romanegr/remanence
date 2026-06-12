# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Directory/listing extraction from decoded disk images (SOFTWARE-SPEC.md §F10).

Commodore images are read natively with the ``d64`` module (BASIC detokenisation
and PETSCII handling included). Other platforms, and a fallback for Commodore,
shell out to host tools: VICE ``c1541``, ``mtools`` ``mdir`` (IBM), AppleCommander
(Apple II). External-tool invocations are documented skeletons run only when the
tool is present.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .errors import PreflightError, RemanenceError

# Image extensions handled natively by the d64 module.
_D64_FAMILY = {".d64", ".d71", ".d80", ".d81", ".d82"}
_IBM_IMAGES = {".img", ".ima"}
_APPLE_IMAGES = {".dsk", ".do", ".po", ".woz"}


def extract_listing(image_path: str | Path, *, encoding: str = "petscii-c64en-uc") -> str:
    """Return a textual directory listing for a decoded disk image.

    Dispatches on the file extension; raises :class:`RemanenceError` for unknown
    formats and :class:`PreflightError` when a needed fallback tool is missing.
    """
    path = Path(image_path)
    if not path.is_file():
        raise RemanenceError(f"image not found: {path}")
    suffix = path.suffix.lower()

    if suffix in _D64_FAMILY:
        return _listing_d64(path, encoding=encoding)
    if suffix in _IBM_IMAGES:
        return _listing_mdir(path)
    if suffix in _APPLE_IMAGES:
        return _listing_applecommander(path)
    raise RemanenceError(f"no listing extractor for format: {suffix}")


def _listing_d64(path: Path, *, encoding: str) -> str:
    """Native Commodore listing via the d64 module; c1541 fallback on failure."""
    try:
        from d64 import DiskImage  # imported lazily so core stays importable without it
    except ImportError:  # pragma: no cover - dependency is pinned
        return _listing_c1541(path)
    try:
        with DiskImage(path, mode="r") as image:
            return "\n".join(image.directory(encoding=encoding))
    except Exception as exc:  # noqa: BLE001 - fall back to the CLI tool
        try:
            return _listing_c1541(path)
        except PreflightError:
            raise RemanenceError(f"could not read {path.name}: {exc}") from exc


def _listing_c1541(path: Path) -> str:
    """VICE c1541 fallback for Commodore images."""
    tool = _require("c1541")
    result = _run([tool, str(path), "-dir"])
    return result.stdout.rstrip()


def _listing_mdir(path: Path) -> str:
    """IBM/FAT directory via mtools mdir."""
    tool = _require("mdir")
    result = _run([tool, "-i", str(path), "::/"])
    return result.stdout.rstrip()


def _listing_applecommander(path: Path) -> str:
    """Apple II directory via AppleCommander (Java)."""
    tool = shutil.which("AppleCommander") or shutil.which("ac")
    if tool is None:
        raise PreflightError("AppleCommander not found (required for Apple II listings)")
    result = _run([tool, "-ls", str(path)])
    return result.stdout.rstrip()


def _require(name: str) -> str:
    tool = shutil.which(name)
    if tool is None:
        raise PreflightError(f"{name} not found (required for this image format)")
    return tool


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RemanenceError(f"listing tool failed: {' '.join(argv)}: {exc}") from exc
