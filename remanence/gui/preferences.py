# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Preferences dialog. Edits a core :class:`Settings` value; no business logic."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import Settings

MEDIA_RATIOS = ["3.5", "5.25", "8"]
LANGUAGES = ["fr", "en"]
THEMES = ["system", "light", "dark"]


class PreferencesDialog(QDialog):
    """Tabbed editor for application settings (paths and defaults)."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Préférences")
        self._settings = settings

        tabs = QTabWidget()
        tabs.addTab(self._build_paths_tab(), "Chemins")
        tabs.addTab(self._build_acquisition_tab(), "Acquisition")
        tabs.addTab(self._build_photos_tab(), "Photos")
        tabs.addTab(self._build_interface_tab(), "Interface")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # -- tabs -------------------------------------------------------------

    def _build_paths_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.pipelines_edit = self._file_row(form, "Registre pipelines", self._settings.pipelines_path)
        self.staging_edit = self._dir_row(form, "Dossier staging", self._settings.staging_root)
        self.catalog_edit = self._dir_row(form, "Racine catalogue", self._settings.catalog_root or "")
        self.blob_stock_edit = self._dir_row(form, "Stock blobs", self._settings.blob_stock or "")
        self.blob_index_edit = self._file_row(form, "Index des blobs", self._settings.blob_index or "")
        return page

    def _build_acquisition_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.operator_edit = QLineEdit(self._settings.default_operator)
        self.device_edit = QLineEdit(self._settings.default_device)
        self.revolutions_spin = QSpinBox()
        self.revolutions_spin.setRange(1, 30)
        self.revolutions_spin.setValue(self._settings.default_revolutions)
        form.addRow("Opérateur par défaut", self.operator_edit)
        form.addRow("Périphérique par défaut", self.device_edit)
        form.addRow("Révolutions par défaut", self.revolutions_spin)
        return page

    def _build_photos_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.ratio_combo = QComboBox()
        self.ratio_combo.addItems(MEDIA_RATIOS)
        self.ratio_combo.setCurrentText(self._settings.default_media_ratio)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(self._settings.jpeg_quality)
        self.long_edge_spin = QSpinBox()
        self.long_edge_spin.setRange(256, 10000)
        self.long_edge_spin.setValue(self._settings.max_long_edge)
        form.addRow("Ratio média par défaut", self.ratio_combo)
        form.addRow("Qualité JPEG", self.quality_spin)
        form.addRow("Bord long max (px)", self.long_edge_spin)
        return page

    def _build_interface_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.language_combo = QComboBox()
        self.language_combo.addItems(LANGUAGES)
        self.language_combo.setCurrentText(self._settings.language)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES)
        self.theme_combo.setCurrentText(self._settings.theme)
        form.addRow("Langue", self.language_combo)
        form.addRow("Thème", self.theme_combo)
        return page

    # -- result -----------------------------------------------------------

    def result_settings(self) -> Settings:
        """Build a Settings value from the current widget state."""
        return Settings(
            pipelines_path=self.pipelines_edit.text() or "pipelines.yaml",
            staging_root=self.staging_edit.text() or "staging",
            catalog_root=self.catalog_edit.text() or None,
            blob_stock=self.blob_stock_edit.text() or None,
            blob_index=self.blob_index_edit.text() or None,
            default_operator=self.operator_edit.text(),
            default_device=self.device_edit.text(),
            default_revolutions=self.revolutions_spin.value(),
            default_media_ratio=self.ratio_combo.currentText(),
            jpeg_quality=self.quality_spin.value(),
            max_long_edge=self.long_edge_spin.value(),
            language=self.language_combo.currentText(),
            theme=self.theme_combo.currentText(),
        )

    # -- helpers ----------------------------------------------------------

    def _file_row(self, form: QFormLayout, label: str, value: str) -> QLineEdit:
        return self._path_row(form, label, value, directory=False)

    def _dir_row(self, form: QFormLayout, label: str, value: str) -> QLineEdit:
        return self._path_row(form, label, value, directory=True)

    def _path_row(self, form: QFormLayout, label: str, value: str, *, directory: bool) -> QLineEdit:
        edit = QLineEdit(value)
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(lambda: self._browse(edit, directory))
        row = QHBoxLayout()
        row.addWidget(edit)
        row.addWidget(browse)
        container = QWidget()
        container.setLayout(row)
        form.addRow(label, container)
        return edit

    def _browse(self, edit: QLineEdit, directory: bool) -> None:
        if directory:
            chosen = QFileDialog.getExistingDirectory(self, "Choisir un dossier", edit.text())
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, "Choisir un fichier", edit.text())
        if chosen:
            edit.setText(chosen)
