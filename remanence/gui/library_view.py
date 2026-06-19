# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Library mode: read-only catalogue browser (SOFTWARE-SPEC.md §F10, §F11).

Delegates entirely to core (catalog, listing, fluxview); never writes.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from ..core import fluxview
from ..core.catalog import BlobIndex, Catalog, CatalogItem, open_catalog
from ..core.errors import RemanenceError
from ..core.listing import extract_listing
from .fluxwidgets import HistogramWidget, TrackMapWidget


class LibraryView(QWidget):
    """Browse, filter, inspect listings, integrity and flux of catalogue items."""

    def __init__(
        self,
        catalog_root: str | Path | None = None,
        blob_index: BlobIndex | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.catalog: Catalog | None = None
        self.blob_index = blob_index or BlobIndex()
        self._items: list[CatalogItem] = []

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("filter by title…")
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.item_list = QListWidget()
        self.item_list.currentRowChanged.connect(self._show_item)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.listing_view = QPlainTextEdit()
        self.listing_view.setReadOnly(True)
        self.histogram = HistogramWidget()
        self.track_map = TrackMapWidget()
        self.integrity_btn = QPushButton("Verify integrity")
        self.integrity_btn.clicked.connect(self._verify_integrity)
        self.integrity_label = QLabel("")

        left = QVBoxLayout()
        left.addWidget(self.filter_edit)
        left.addWidget(self.item_list)
        left_widget = QWidget()
        left_widget.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(QLabel("Item"))
        right.addWidget(self.detail)
        right.addWidget(QLabel("Listing"))
        right.addWidget(self.listing_view)
        right.addWidget(QLabel("Flux histogram"))
        right.addWidget(self.histogram)
        right.addWidget(QLabel("Track map"))
        right.addWidget(self.track_map)
        right.addWidget(self.integrity_btn)
        right.addWidget(self.integrity_label)
        right_widget = QWidget()
        right_widget.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        layout = QHBoxLayout(self)
        layout.addWidget(splitter)

        if catalog_root is not None:
            self.open(catalog_root, self.blob_index)

    def open(self, catalog_root: str | Path, blob_index: BlobIndex | None = None) -> None:
        self.catalog = open_catalog(catalog_root, blob_index or self.blob_index)
        self.blob_index = blob_index or self.blob_index
        self.refresh()

    def apply_settings(self, settings) -> None:
        """Load the blob index and open the catalogue from settings, if configured."""
        if settings.blob_index and Path(settings.blob_index).is_file():
            self.blob_index = BlobIndex.from_file(settings.blob_index)
        if settings.catalog_root and Path(settings.catalog_root).is_dir():
            self.open(settings.catalog_root, self.blob_index)

    def refresh(self) -> None:
        if self.catalog is None:
            return
        self._items = list(self.catalog.iter_items())
        self._apply_filter()

    def _apply_filter(self) -> None:
        text = self.filter_edit.text().lower()
        self.item_list.clear()
        self._filtered = [i for i in self._items if text in i.title.lower()]
        for item in self._filtered:
            self.item_list.addItem(f"{item.title} [{item.platform}] — {item.status}")

    def current_item(self) -> CatalogItem | None:
        row = self.item_list.currentRow()
        if 0 <= row < len(self._filtered):
            return self._filtered[row]
        return None

    def _show_item(self, row: int) -> None:
        item = self.current_item()
        if item is None:
            return
        lines = [f"Title: {item.title}", f"Platform: {item.platform}",
                 f"Status: {item.status}", f"Disks: {len(item.disks)}"]
        self.detail.setPlainText("\n".join(lines))
        self._show_listing(item)
        self._show_flux(item)
        self.integrity_label.setText("")

    def _show_listing(self, item: CatalogItem) -> None:
        self.listing_view.clear()
        for disk in item.disks:
            for entry in disk.get("files", []):
                if entry.get("role") == "image":
                    blob = self.blob_index.resolve(entry.get("sha256", ""))
                    if blob is not None and blob.is_file():
                        try:
                            self.listing_view.appendPlainText(str(extract_listing(blob)))
                        except RemanenceError as exc:
                            self.listing_view.appendPlainText(f"(listing unavailable: {exc})")
                    return

    def _show_flux(self, item: CatalogItem) -> None:
        for disk in item.disks:
            for entry in disk.get("files", []):
                if entry.get("role") == "flux":
                    blob = self.blob_index.resolve(entry.get("sha256", ""))
                    if blob is not None and blob.is_file():
                        capture = fluxview.parse_scp(blob)
                        counts, _ = fluxview.flux_histogram(capture)
                        self.histogram.set_histogram(counts)
                        self.track_map.set_track_map(fluxview.track_map(capture))
                    return

    def _verify_integrity(self) -> None:
        item = self.current_item()
        if item is None or self.catalog is None:
            return
        issues = self.catalog.verify_integrity(item)
        if not issues:
            self.integrity_label.setText("integrity OK")
        else:
            self.integrity_label.setText(
                "; ".join(f"{i.disk_id}: {i.kind}" for i in issues)
            )
