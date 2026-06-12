# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""GUI entry point and main window (Dump + Library modes)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from .dump_view import DumpView
from .library_view import LibraryView


class MainWindow(QMainWindow):
    """Top-level window hosting the Dump and Library modes as tabs."""

    def __init__(
        self,
        registry_path: str | Path = "pipelines.yaml",
        staging_root: str | Path = "staging",
        catalog_root: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("remanence")
        tabs = QTabWidget()
        self.dump_view = DumpView(registry_path, staging_root)
        self.library_view = LibraryView(catalog_root)
        tabs.addTab(self.dump_view, "Dump")
        tabs.addTab(self.library_view, "Library")
        self.setCentralWidget(tabs)


def run(
    registry_path: str | Path = "pipelines.yaml",
    staging_root: str | Path = "staging",
    catalog_root: str | Path | None = None,
) -> int:
    """Launch the GUI event loop."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(registry_path, staging_root, catalog_root)
    window.resize(900, 650)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
