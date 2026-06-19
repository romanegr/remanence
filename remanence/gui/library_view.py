# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Library mode: read-only catalogue browser (SOFTWARE-SPEC.md §F10, §F11).

Left: a sortable, filterable table of dumped disks (spreadsheet style). Right: a
details panel for the selected item (metadata, listing, flux histogram and track
map, integrity). Delegates entirely to core; never writes.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..core import fluxview
from ..core.catalog import BlobIndex, Catalog, CatalogItem, open_catalog
from ..core.errors import RemanenceError
from ..core.listing import extract_listing
from .fluxwidgets import HistogramWidget, TrackMapWidget

# Table columns and their indices.
COLUMNS = ["Titre", "Plateforme", "Éditeur", "Date", "Statut",
           "Type", "Disques", "Préservation", "Copyright"]
COL_TITLE, COL_PLATFORM, COL_STATUS = 0, 1, 4
ITEM_ROLE = Qt.UserRole + 1
ALL = "Tous"


class CatalogFilterProxy(QSortFilterProxyModel):
    """Multi-criteria row filter over the catalogue table model."""

    def __init__(self) -> None:
        super().__init__()
        self._text = ""
        self._platform = ""
        self._status = ""

    def set_text(self, value: str) -> None:
        self._text = value.lower()
        self.invalidate()

    def set_platform(self, value: str) -> None:
        self._platform = "" if value == ALL else value
        self.invalidate()

    def set_status(self, value: str) -> None:
        self._status = "" if value == ALL else value
        self.invalidate()

    def filterAcceptsRow(self, row: int, parent) -> bool:  # noqa: N802 - Qt override
        model = self.sourceModel()

        def cell(col: int) -> str:
            return str(model.index(row, col, parent).data() or "")

        if self._text and self._text not in cell(COL_TITLE).lower():
            return False
        if self._platform and cell(COL_PLATFORM) != self._platform:
            return False
        if self._status and cell(COL_STATUS) != self._status:
            return False
        return True


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

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_table_panel())
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout = QHBoxLayout(self)
        layout.addWidget(splitter)

        if catalog_root is not None:
            self.open(catalog_root, self.blob_index)

    # -- left: filterable table ------------------------------------------

    def _build_table_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        filters = QHBoxLayout()
        self.text_filter = QLineEdit()
        self.text_filter.setPlaceholderText("filtrer par titre…")
        self.platform_filter = QComboBox()
        self.status_filter = QComboBox()
        filters.addWidget(self.text_filter)
        filters.addWidget(QLabel("Plateforme"))
        filters.addWidget(self.platform_filter)
        filters.addWidget(QLabel("Statut"))
        filters.addWidget(self.status_filter)
        layout.addLayout(filters)

        self.model = QStandardItemModel(0, len(COLUMNS))
        self.model.setHorizontalHeaderLabels(COLUMNS)
        self.proxy = CatalogFilterProxy()
        self.proxy.setSourceModel(self.model)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.text_filter.textChanged.connect(self.proxy.set_text)
        self.platform_filter.currentTextChanged.connect(self.proxy.set_platform)
        self.status_filter.currentTextChanged.connect(self.proxy.set_status)
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        return panel

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.listing_view = QPlainTextEdit()
        self.listing_view.setReadOnly(True)
        self.histogram = HistogramWidget()
        self.track_map = TrackMapWidget()
        self.integrity_btn = QPushButton("Vérifier l'intégrité")
        self.integrity_btn.clicked.connect(self._verify_integrity)
        self.integrity_label = QLabel("")
        layout.addWidget(QLabel("Élément"))
        layout.addWidget(self.detail)
        layout.addWidget(QLabel("Listing"))
        layout.addWidget(self.listing_view)
        layout.addWidget(QLabel("Histogramme de flux"))
        layout.addWidget(self.histogram)
        layout.addWidget(QLabel("Carte de piste"))
        layout.addWidget(self.track_map)
        layout.addWidget(self.integrity_btn)
        layout.addWidget(self.integrity_label)
        return panel

    # -- data -------------------------------------------------------------

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
        self._populate_table()
        self._populate_filter_choices()

    def _populate_table(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        for item in self._items:
            self.model.appendRow(self._row_for(item))

    def _row_for(self, item: CatalogItem) -> list[QStandardItem]:
        cells = [
            item.title,
            item.platform,
            item.item.get("publisher", ""),
            str(item.item.get("date", "")),
            item.status,
            item.item.get("kind", ""),
            str(len(item.disks)),
            self._preservation(item),
            item.item.get("copyright_status", ""),
        ]
        row = [QStandardItem(text) for text in cells]
        row[0].setData(item, ITEM_ROLE)  # keep the item on its title cell
        return row

    @staticmethod
    def _preservation(item: CatalogItem) -> str:
        for disk in item.disks:
            level = disk.get("acquisition", {}).get("preservation_level")
            if level:
                return level
        return ""

    def _populate_filter_choices(self) -> None:
        platforms = sorted({i.platform for i in self._items if i.platform})
        statuses = sorted({i.status for i in self._items if i.status})
        self._reset_combo(self.platform_filter, platforms)
        self._reset_combo(self.status_filter, statuses)

    @staticmethod
    def _reset_combo(combo: QComboBox, values: list[str]) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(ALL)
        combo.addItems(values)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    # -- selection / details ---------------------------------------------

    def current_item(self) -> CatalogItem | None:
        index = self.table.currentIndex()
        if not index.isValid():
            return None
        source = self.proxy.mapToSource(index)
        title_cell = self.model.item(source.row(), COL_TITLE)
        return title_cell.data(ITEM_ROLE) if title_cell is not None else None

    def _on_row_changed(self, *_args) -> None:
        item = self.current_item()
        if item is not None:
            self._show_item(item)

    def _show_item(self, item: CatalogItem) -> None:
        lines = [
            f"Titre : {item.title}",
            f"Plateforme : {item.platform}",
            f"Éditeur : {item.item.get('publisher', '')}",
            f"Statut : {item.status}",
            f"Copyright : {item.item.get('copyright_status', '')}",
            f"Disques : {len(item.disks)}",
        ]
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
                            self.listing_view.appendPlainText(f"(listing indisponible : {exc})")
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
            self.integrity_label.setText("intégrité OK")
        else:
            self.integrity_label.setText(
                "; ".join(f"{i.disk_id}: {i.kind}" for i in issues)
            )
