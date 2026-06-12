# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Run staging: atomic writes, temporary names, session reopening (F6, F9).

A *run* is a directory ``staging/<run_id>/`` holding the deliverable of a single
disk: flux variants, decoded image, normalised photos, listing, label text and
``manifest.yaml``. All writes are atomic and never silently overwrite an existing
file (SOFTWARE-SPEC.md §F2, §7 non-functional requirements).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .errors import StagingError

PHOTOS_SUBDIR = "photos"
LISTINGS_SUBDIR = "listings"
MANIFEST_NAME = "manifest.yaml"

# Temporary-name templates per role (CONVENTIONS.md §5 examples).
_TEMP_TEMPLATES = {
    "flux": "flux_read{n:02d}.{ext}",
}
_DEFAULT_TEMPLATE = "{role}{n:02d}.{ext}"


def _atomic_write_bytes(dest: Path, data: bytes) -> None:
    """Write ``data`` to ``dest`` atomically (temp file + fsync + os.replace)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-", suffix=dest.suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, dest)
    except BaseException:
        # Leave no half-written temp file behind on failure.
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


class StagingRun:
    """A single staging run directory.

    Writes are confined to the run directory; any attempt to escape it (absolute
    paths, ``..``) raises :class:`StagingError`.
    """

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id
        self._temp_counters: dict[str, int] = {}

    # -- path helpers -----------------------------------------------------

    @property
    def photos_dir(self) -> Path:
        return self.path / PHOTOS_SUBDIR

    @property
    def listings_dir(self) -> Path:
        return self.path / LISTINGS_SUBDIR

    @property
    def manifest_path(self) -> Path:
        return self.path / MANIFEST_NAME

    def _resolve(self, rel: str | Path) -> Path:
        """Resolve a run-relative path, refusing anything outside the run dir."""
        rel = Path(rel)
        if rel.is_absolute():
            raise StagingError(f"path must be relative to the run: {rel}")
        target = (self.path / rel).resolve()
        root = self.path.resolve()
        if root != target and root not in target.parents:
            raise StagingError(f"refusing to write outside the run: {rel}")
        return target

    # -- naming -----------------------------------------------------------

    def alloc_temp(self, role: str, ext: str) -> str:
        """Allocate the next temporary file name for ``role`` (e.g. ``flux``).

        Returns a bare file name (relative to the run), never touching the disk.
        Naming follows CONVENTIONS.md §5 (``flux_read01.scp``, ``image01.d64``).
        """
        ext = ext.lstrip(".")
        n = self._temp_counters.get(role, 0) + 1
        self._temp_counters[role] = n
        template = _TEMP_TEMPLATES.get(role, _DEFAULT_TEMPLATE)
        return template.format(role=role, n=n, ext=ext)

    # -- writes -----------------------------------------------------------

    def write_atomic(self, rel: str | Path, data: bytes | str, *, overwrite: bool = False) -> Path:
        """Atomically write ``data`` to a run-relative path; return the full path."""
        target = self._resolve(rel)
        if target.exists() and not overwrite:
            raise StagingError(f"refusing to overwrite existing file: {rel}")
        payload = data.encode("utf-8") if isinstance(data, str) else data
        _atomic_write_bytes(target, payload)
        return target

    def add_file(self, src: str | Path, rel: str | Path, *, overwrite: bool = False) -> Path:
        """Atomically copy ``src`` into the run at ``rel``; return the full path."""
        src = Path(src)
        if not src.is_file():
            raise StagingError(f"source file does not exist: {src}")
        target = self._resolve(rel)
        if target.exists() and not overwrite:
            raise StagingError(f"refusing to overwrite existing file: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".tmp-", suffix=target.suffix)
        os.close(fd)
        try:
            shutil.copyfile(src, tmp_name)
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
        return target


def create_run(staging_root: str | Path, run_id: str | None = None) -> StagingRun:
    """Create a fresh run directory under ``staging_root``.

    ``run_id`` defaults to ``YYYY-MM-DD_runNN`` derived from the current date and
    the first free sequence number. Refuses to clobber an existing run.
    """
    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    if run_id is None:
        run_id = _next_run_id(staging_root)
    run_path = staging_root / run_id
    if run_path.exists():
        raise StagingError(f"run already exists: {run_path}")
    run_path.mkdir(parents=False)
    return StagingRun(run_path, run_id)


def reopen_run(run_path: str | Path) -> StagingRun:
    """Reopen an existing run to add photos or metadata (SOFTWARE-SPEC.md §F9)."""
    run_path = Path(run_path)
    if not run_path.is_dir():
        raise StagingError(f"run directory not found: {run_path}")
    return StagingRun(run_path, run_path.name)


def _next_run_id(staging_root: Path) -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    n = 1
    while (staging_root / f"{day}_run{n:02d}").exists():
        n += 1
    return f"{day}_run{n:02d}"
