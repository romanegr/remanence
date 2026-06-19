# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""GUI smoke tests (offscreen). Skipped if PySide6 is unavailable."""

from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml import YAML

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from remanence.core.catalog import BlobIndex  # noqa: E402
from remanence.core.hashing import sha256_file  # noqa: E402
from remanence.core.manifest import load_manifest  # noqa: E402
from remanence.core.settings import Settings  # noqa: E402
from remanence.fixtures import asset_path  # noqa: E402
from remanence.gui.app import MainWindow  # noqa: E402
from remanence.gui.dump_view import DumpView  # noqa: E402
from remanence.gui.library_view import LibraryView  # noqa: E402
from remanence.gui.preferences import PreferencesDialog  # noqa: E402

EXAMPLE = str(Path(__file__).resolve().parents[1] / "pipelines.example.yaml")
YAML_RT = YAML()


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        YAML_RT.dump(data, handle)


def test_dump_view_full_flow_offscreen(qtbot, tmp_path, monkeypatch):
    # Modal dialogs would block the offscreen event loop; stub them.
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    view = DumpView(EXAMPLE, str(tmp_path))
    qtbot.addWidget(view)
    view.pipeline_combo.setCurrentText("fixture-c64")
    view.operator_edit.setText("tester")

    # Synchronous acquisition keeps the test deterministic.
    view.start_acquire(best=True, blocking=True)
    assert len(view.session.flux) == 1
    assert view.session.assessment().preservation_level == "gold"

    # Re-read adds a distinct variant (F3).
    view.start_acquire(best=False, blocking=True)
    assert len(view.session.flux) == 2

    view.label_edit.setPlainText("REMANENCE DEMO")
    path = view.finalize()
    assert path is not None
    manifest = load_manifest(path)
    assert manifest["pipeline_id"] == "fixture-c64"
    assert len([f for f in manifest["files"] if f["role"] == "flux"]) == 2


def test_dump_view_keep_flux_only(qtbot, tmp_path):
    view = DumpView(EXAMPLE, str(tmp_path))
    qtbot.addWidget(view)
    view.pipeline_combo.setCurrentText("fixture-c64")
    view.start_acquire(best=True, blocking=True)
    view._keep_flux_only()
    verdict = view.session.assessment()
    assert verdict.preservation_level == "silver"
    assert verdict.state == "unstable"


def test_library_view_browse_and_flux(qtbot, tmp_path):
    d64 = asset_path("fixture_disk.d64")
    scp = asset_path("fixture_disk.scp")
    sha_d64, sha_scp = sha256_file(d64), sha256_file(scp)

    item_dir = tmp_path / "catalog" / "commodore-c64" / "demo-1985-acme-c64"
    _write_yaml(item_dir / "item.yaml", {
        "schema_version": 1, "status": "ready", "title": "Demo Game",
        "kind": "single_title", "platform": "commodore-c64",
        "copyright_status": "freeware", "disks": ["disk-01"],
    })
    _write_yaml(item_dir / "disks" / "disk-01.yaml", {
        "schema_version": 1, "disk_id": "disk-01",
        "acquisition": {"method": "greaseweazle", "preservation_level": "gold"},
        "files": [
            {"role": "flux", "format": "scp", "sha256": sha_scp, "upload": True},
            {"role": "image", "format": "d64", "sha256": sha_d64, "upload": True},
        ],
    })

    index = BlobIndex({sha_d64: str(d64), sha_scp: str(scp)})
    view = LibraryView(tmp_path / "catalog", index)
    qtbot.addWidget(view)
    assert view.proxy.rowCount() == 1
    view.table.selectRow(0)
    assert view.current_item().title == "Demo Game"
    assert "Demo Game" in view.detail.toPlainText()
    assert "REMANENCE DEMO" in view.listing_view.toPlainText()
    view._verify_integrity()
    assert "OK" in view.integrity_label.text()


def test_library_table_filters(qtbot, tmp_path):
    def _item(slug, title, platform, status, publisher):
        item_dir = tmp_path / "catalog" / platform / slug
        _write_yaml(item_dir / "item.yaml", {
            "schema_version": 1, "status": status, "title": title,
            "kind": "single_title", "platform": platform, "publisher": publisher,
            "copyright_status": "freeware", "disks": ["disk-01"],
        })
        _write_yaml(item_dir / "disks" / "disk-01.yaml", {
            "schema_version": 1, "disk_id": "disk-01",
            "acquisition": {"method": "greaseweazle", "preservation_level": "gold"},
            "files": [{"role": "image", "format": "d64", "sha256": "0" * 64, "upload": True}],
        })

    _item("alpha-c64", "Alpha", "commodore-c64", "ready", "Acme")
    _item("beta-c64", "Beta", "commodore-c64", "draft", "Acme")
    _item("gamma-apple", "Gamma", "apple-ii", "ready", "Other")

    view = LibraryView(tmp_path / "catalog", BlobIndex({}))
    qtbot.addWidget(view)
    assert view.proxy.rowCount() == 3

    view.text_filter.setText("eta")          # matches "Beta" only
    assert view.proxy.rowCount() == 1
    view.text_filter.setText("")

    view.proxy.set_platform("apple-ii")
    assert view.proxy.rowCount() == 1
    view.proxy.set_platform("Tous")

    view.proxy.set_status("ready")
    assert view.proxy.rowCount() == 2

    # Sorting by title works (spreadsheet behaviour).
    view.table.sortByColumn(0, Qt.AscendingOrder)
    view.table.selectRow(0)
    assert view.current_item() is not None


def test_main_window_constructs_with_settings(qtbot, tmp_path):
    window = MainWindow(Settings(pipelines_path=EXAMPLE, staging_root=str(tmp_path)))
    qtbot.addWidget(window)
    assert window.dump_view is not None
    assert window.library_view is not None
    assert window.menuBar().actions()  # menu bar is populated


def test_main_window_has_expected_menus(qtbot, tmp_path):
    window = MainWindow(Settings(pipelines_path=EXAMPLE, staging_root=str(tmp_path)))
    qtbot.addWidget(window)
    menu_titles = [a.text() for a in window.menuBar().actions()]
    assert menu_titles == ["&Fichier", "&Édition", "&Affichage", "&Outils", "Aid&e"]


def test_preferences_dialog_round_trips_settings(qtbot):
    settings = Settings(staging_root="/data/staging", default_operator="rn",
                        default_revolutions=7, theme="dark", default_media_ratio="3.5")
    dialog = PreferencesDialog(settings)
    qtbot.addWidget(dialog)
    result = dialog.result_settings()
    assert result.staging_root == "/data/staging"
    assert result.default_operator == "rn"
    assert result.default_revolutions == 7
    assert result.theme == "dark"
    assert result.default_media_ratio == "3.5"
    result.validate()  # stays schema-valid


def test_preferences_edit_updates_result(qtbot):
    dialog = PreferencesDialog(Settings())
    qtbot.addWidget(dialog)
    dialog.operator_edit.setText("operator-x")
    dialog.quality_spin.setValue(95)
    result = dialog.result_settings()
    assert result.default_operator == "operator-x"
    assert result.jpeg_quality == 95


def test_apply_settings_reloads_dump_view(qtbot, tmp_path):
    window = MainWindow(Settings(staging_root=str(tmp_path)))
    qtbot.addWidget(window)
    window.apply_settings(Settings(pipelines_path=EXAMPLE, staging_root=str(tmp_path),
                                   default_operator="auto"))
    assert window.dump_view.registry is not None
    assert window.dump_view.operator_edit.text() == "auto"


def test_resume_run_in_dump_view(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    # First produce a run via a session-backed dump.
    view = DumpView(EXAMPLE, str(tmp_path))
    qtbot.addWidget(view)
    view.pipeline_combo.setCurrentText("fixture-c64")
    view.operator_edit.setText("tester")
    view.start_acquire(best=True, blocking=True)
    view.finalize()
    run_path = view.session.run.path

    # Reopen it in a fresh view.
    view2 = DumpView(EXAMPLE, str(tmp_path))
    qtbot.addWidget(view2)
    view2.resume_run(run_path)
    assert len(view2.session.flux) == 1
    assert view2.session.run.run_id == run_path.name
