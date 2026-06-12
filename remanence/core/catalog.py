# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Read-only catalogue access for the Library mode (SOFTWARE-SPEC.md §F10).

Reads the Git-versioned metadata (``item.yaml``, per-disk ``disk-NN.yaml``,
``contents.yaml``) and resolves the flux/image blobs from the local stock *by
sha256* (CONVENTIONS.md §7) — never by name. This module never writes to the
catalogue or the blobs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ruamel.yaml import YAML

from . import schema
from .errors import IntegrityError, RemanenceError
from .hashing import sha256_file


def _load_yaml(path: Path) -> Any:
    yaml = YAML(typ="safe")
    with open(path, "rb") as handle:
        return yaml.load(handle)


class BlobIndex:
    """Maps ``sha256`` to a filesystem path in the out-of-repo blob stock."""

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._map: dict[str, Path] = {k: Path(v) for k, v in (mapping or {}).items()}

    @classmethod
    def from_file(cls, path: str | Path) -> "BlobIndex":
        with open(path, "rb") as handle:
            return cls(json.load(handle))

    def resolve(self, sha256: str) -> Path | None:
        return self._map.get(sha256)

    def __contains__(self, sha256: str) -> bool:
        return sha256 in self._map


@dataclass
class CatalogItem:
    slug: str
    path: Path
    item: dict[str, Any]
    disks: list[dict[str, Any]] = field(default_factory=list)
    contents: dict[str, Any] | None = None

    @property
    def title(self) -> str:
        return self.item.get("title", "")

    @property
    def platform(self) -> str:
        return self.item.get("platform", "")

    @property
    def status(self) -> str:
        return self.item.get("status", "")


@dataclass
class IntegrityIssue:
    disk_id: str
    sha256: str
    kind: str          # "missing" | "corrupted"
    detail: str


class Catalog:
    """A browsable, read-only view over a ``catalog/`` tree."""

    def __init__(self, root: Path, blob_index: BlobIndex | None = None) -> None:
        self.root = root
        self.blob_index = blob_index or BlobIndex()

    def iter_items(self) -> Iterator[CatalogItem]:
        for item_yaml in sorted(self.root.glob("*/*/item.yaml")):
            yield self._load_item(item_yaml.parent)

    def filter(
        self,
        *,
        platform: str | None = None,
        status: str | None = None,
        publisher: str | None = None,
        text: str | None = None,
    ) -> list[CatalogItem]:
        results = []
        for item in self.iter_items():
            if platform and item.platform != platform:
                continue
            if status and item.status != status:
                continue
            if publisher and item.item.get("publisher") != publisher:
                continue
            if text and text.lower() not in item.title.lower():
                continue
            results.append(item)
        return results

    def get(self, slug: str) -> CatalogItem:
        for item_yaml in self.root.glob(f"*/{slug}/item.yaml"):
            return self._load_item(item_yaml.parent)
        raise RemanenceError(f"item not found: {slug}")

    def resolve_blob(self, sha256: str) -> Path | None:
        return self.blob_index.resolve(sha256)

    def verify_integrity(self, item: CatalogItem) -> list[IntegrityIssue]:
        """Re-check every disk blob's sha256 against the catalogue metadata."""
        issues: list[IntegrityIssue] = []
        for disk in item.disks:
            disk_id = disk.get("disk_id", "?")
            for entry in disk.get("files", []):
                sha = entry.get("sha256", "")
                blob = self.blob_index.resolve(sha)
                if blob is None or not blob.is_file():
                    issues.append(IntegrityIssue(disk_id, sha, "missing",
                                                 "blob absent from the stock"))
                    continue
                actual = sha256_file(blob)
                if actual != sha:
                    issues.append(IntegrityIssue(disk_id, sha, "corrupted",
                                                 f"on-disk sha256 is {actual}"))
        return issues

    # -- internals --------------------------------------------------------

    def _load_item(self, item_dir: Path) -> CatalogItem:
        item_data = _to_plain(_load_yaml(item_dir / "item.yaml"))
        schema.validate(item_data, "item")

        contents = None
        contents_path = item_dir / "contents.yaml"
        if contents_path.is_file():
            contents = _to_plain(_load_yaml(contents_path))
            schema.validate(contents, "contents")

        disks = []
        for disk_id in item_data.get("disks", []):
            disk_path = self._disk_path(item_dir, disk_id)
            if disk_path is None:
                raise RemanenceError(f"disk file missing for {disk_id} in {item_dir.name}")
            disk_data = _to_plain(_load_yaml(disk_path))
            schema.validate(disk_data, "disk")
            disks.append(disk_data)

        return CatalogItem(slug=item_dir.name, path=item_dir, item=item_data,
                           disks=disks, contents=contents)

    @staticmethod
    def _disk_path(item_dir: Path, disk_id: str) -> Path | None:
        for candidate in (item_dir / "disks" / f"{disk_id}.yaml", item_dir / f"{disk_id}.yaml"):
            if candidate.is_file():
                return candidate
        return None


def open_catalog(catalog_root: str | Path, blob_index: BlobIndex | None = None) -> Catalog:
    """Open a catalogue tree rooted at ``catalog_root`` (read-only)."""
    root = Path(catalog_root)
    if not root.is_dir():
        raise RemanenceError(f"catalog root not found: {root}")
    return Catalog(root, blob_index)


def _to_plain(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _to_plain(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_to_plain(v) for v in data]
    return data
