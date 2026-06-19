# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""GUI entry point and main window (menu bar, status bar, preferences).

Orchestrates core only; all configuration lives in a core :class:`Settings`
value loaded at startup and edited through the Preferences dialog.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QAction, QKeySequence, QPalette, QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

from .. import __version__
from ..core import preflight
from ..core.errors import RemanenceError
from ..core.pipelines import load_pipelines
from ..core.settings import Settings, load_settings, save_settings
from .dump_view import DumpView
from .library_view import LibraryView
from .preferences import PreferencesDialog

DUMP_TAB = 0
LIBRARY_TAB = 1


class MainWindow(QMainWindow):
    """Top-level window with menus, mode tabs and a status bar."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or Settings()
        self.setWindowTitle("remanence")

        self.tabs = QTabWidget()
        self.dump_view = DumpView(self.settings.pipelines_path, self.settings.staging_root)
        self.library_view = LibraryView()
        self.tabs.addTab(self.dump_view, "Dump")
        self.tabs.addTab(self.library_view, "Bibliothèque")
        self.setCentralWidget(self.tabs)

        self._build_menus()
        self.statusBar().showMessage("Prêt")
        self.dump_view.manifest_written.connect(
            lambda path: self.statusBar().showMessage(f"Manifeste écrit : {path}")
        )

        self.apply_settings(self.settings)

    # -- menus ------------------------------------------------------------

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&Fichier")
        self._add_action(file_menu, "Nouveau dump", self._new_dump, QKeySequence.New)
        self._add_action(file_menu, "Ouvrir un run…", self._open_run, QKeySequence.Open)
        self._add_action(file_menu, "Ouvrir un catalogue…", self._open_catalog)
        file_menu.addSeparator()
        self._add_action(file_menu, "Quitter", self.close, QKeySequence.Quit)

        edit_menu = menubar.addMenu("&Édition")
        self._add_action(edit_menu, "Préférences…", self._open_preferences,
                         QKeySequence(Qt.CTRL | Qt.Key_Comma))

        view_menu = menubar.addMenu("&Affichage")
        self._add_action(view_menu, "Mode Dump", lambda: self.tabs.setCurrentIndex(DUMP_TAB))
        self._add_action(view_menu, "Mode Bibliothèque",
                         lambda: self.tabs.setCurrentIndex(LIBRARY_TAB))

        tools_menu = menubar.addMenu("&Outils")
        self._add_action(tools_menu, "Vérifier la configuration", self._run_preflight)
        self._add_action(tools_menu, "Vérifier l'intégrité du catalogue",
                         self._verify_integrity)

        help_menu = menubar.addMenu("Aid&e")
        self._add_action(help_menu, "À propos de remanence", self._about)

    def _add_action(self, menu, text, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    # -- settings ---------------------------------------------------------

    def apply_settings(self, settings: Settings) -> None:
        """Apply settings to the application and both views."""
        self.settings = settings
        _apply_theme(QApplication.instance(), settings.theme)
        self.dump_view.apply_settings(settings)
        self.library_view.apply_settings(settings)

    def _open_preferences(self) -> None:
        dialog = PreferencesDialog(self.settings, self)
        if dialog.exec() == PreferencesDialog.Accepted:
            new_settings = dialog.result_settings()
            try:
                save_settings(new_settings)
            except RemanenceError as exc:
                QMessageBox.warning(self, "Préférences", f"Impossible d'enregistrer : {exc}")
                return
            self.apply_settings(new_settings)
            self.statusBar().showMessage("Préférences enregistrées")

    # -- file actions -----------------------------------------------------

    def _new_dump(self) -> None:
        self.dump_view.reset_session()
        self.tabs.setCurrentIndex(DUMP_TAB)
        self.statusBar().showMessage("Nouveau dump")

    def _open_run(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Ouvrir un run", self.settings.staging_root)
        if not path:
            return
        try:
            self.dump_view.resume_run(path)
        except RemanenceError as exc:
            QMessageBox.warning(self, "Ouvrir un run", str(exc))
            return
        self.tabs.setCurrentIndex(DUMP_TAB)
        self.statusBar().showMessage(f"Run rouvert : {path}")

    def _open_catalog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Ouvrir un catalogue",
                                                self.settings.catalog_root or "")
        if not path:
            return
        try:
            self.library_view.open(path, self.library_view.blob_index)
        except RemanenceError as exc:
            QMessageBox.warning(self, "Ouvrir un catalogue", str(exc))
            return
        self.tabs.setCurrentIndex(LIBRARY_TAB)

    # -- tools actions ----------------------------------------------------

    def _run_preflight(self) -> None:
        try:
            registry = load_pipelines(self.settings.pipelines_path)
        except (RemanenceError, OSError) as exc:
            QMessageBox.warning(self, "Préflight", f"Registre invalide : {exc}")
            return
        report = preflight.check_registry(registry)
        lines = [f"Registre valide : {len(registry.pipelines())} pipelines", ""]
        for name, status in sorted(report.tools.items()):
            mark = "OK" if status.found else "MANQUANT"
            lines.append(f"  [{mark}] {name}")
        lines.append("")
        for pipeline in registry.pipelines():
            ready = "prêt" if report.pipeline_ready[pipeline.id] else "bloqué"
            lines.append(f"  {ready} — {pipeline.id}")
        QMessageBox.information(self, "Vérification de la configuration", "\n".join(lines))

    def _verify_integrity(self) -> None:
        item = self.library_view.current_item()
        if item is None or self.library_view.catalog is None:
            QMessageBox.information(self, "Intégrité",
                                   "Sélectionnez un item dans la bibliothèque.")
            return
        issues = self.library_view.catalog.verify_integrity(item)
        if not issues:
            QMessageBox.information(self, "Intégrité", f"{item.title} : intégrité OK")
        else:
            detail = "\n".join(f"{i.disk_id}: {i.kind} — {i.detail}" for i in issues)
            QMessageBox.warning(self, "Intégrité", detail)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "À propos de remanence",
            f"<b>remanence</b> {__version__}<br>"
            "Acquisition de disquettes et consultation du catalogue.<br>"
            "Licence CeCILL-2.1.",
        )


def _apply_theme(app: QApplication | None, theme: str) -> None:
    """Apply a minimal palette for the chosen theme (system/light/dark)."""
    if app is None:
        return
    if theme == "dark":
        app.setStyle("Fusion")
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(37, 37, 38))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        app.setPalette(palette)
    else:
        app.setPalette(QPalette())  # back to default


def run(settings: Settings | None = None) -> int:
    """Launch the GUI event loop. Loads XDG settings when none are supplied."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(settings or load_settings())
    window.resize(960, 700)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
