# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Dump mode: a stepwise wizard orchestrating DumpSession (SOFTWARE-SPEC.md §8).

The view holds no business logic; every action delegates to
:class:`remanence.core.session.DumpSession` and the other core modules.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import preflight
from ..core.errors import RemanenceError
from ..core.pipelines import Pipeline, PipelineRegistry, load_pipelines
from ..core.runner import Runner
from ..core.session import DumpSession, load_session
from ..core.settings import Settings
from ..core.staging import create_run
from ..core.images import EditOps
from .worker import AcquireWorker, run_in_thread

PHOTO_TYPES = ["front", "back", "label", "sleeve", "manual", "other"]


class DumpView(QWidget):
    """Five-step dump wizard."""

    manifest_written = Signal(str)

    def __init__(
        self,
        registry_path: str | Path = "pipelines.yaml",
        staging_root: str | Path = "staging",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.registry_path = str(registry_path)
        self.staging_root = str(staging_root)
        self.registry: PipelineRegistry | None = None
        self.session: DumpSession | None = None
        self._thread = None
        self._worker = None

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_select_page())
        self.stack.addWidget(self._build_acquire_page())
        self.stack.addWidget(self._build_photos_page())
        self.stack.addWidget(self._build_metadata_page())
        self.stack.addWidget(self._build_summary_page())

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.next_btn = QPushButton("Next")
        self.back_btn.clicked.connect(self._go_back)
        self.next_btn.clicked.connect(self._go_next)
        nav.addWidget(self.back_btn)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)
        layout.addLayout(nav)

        self.load_registry(self.registry_path)

    # -- page 1: format & pipeline ---------------------------------------

    def _build_select_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.format_combo = QComboBox()
        self.pipeline_combo = QComboBox()
        self.device_edit = QLineEdit()
        self.revs_spin = QSpinBox()
        self.revs_spin.setRange(1, 30)
        self.revs_spin.setValue(5)
        self.preflight_label = QLabel("")
        self.preflight_label.setWordWrap(True)

        self.format_combo.currentTextChanged.connect(self._refresh_pipelines)
        self.pipeline_combo.currentTextChanged.connect(self._refresh_preflight)

        layout.addRow("Format", self.format_combo)
        layout.addRow("Pipeline", self.pipeline_combo)
        layout.addRow("Device", self.device_edit)
        layout.addRow("Revolutions", self.revs_spin)
        layout.addRow("Preflight", self.preflight_label)
        return page

    def load_registry(self, path: str | Path) -> None:
        try:
            self.registry = load_pipelines(path)
        except (RemanenceError, OSError) as exc:
            self.preflight_label.setText(f"cannot load pipelines: {exc}")
            return
        self.format_combo.clear()
        self.format_combo.addItems([f.id for f in self.registry.formats()])
        self._refresh_pipelines()

    def _refresh_pipelines(self) -> None:
        if self.registry is None:
            return
        self.pipeline_combo.clear()
        for pipeline in self.registry.pipelines(self.format_combo.currentText()):
            self.pipeline_combo.addItem(pipeline.id)
        self._refresh_preflight()

    def _refresh_preflight(self) -> None:
        pipeline = self.current_pipeline()
        if pipeline is None:
            return
        statuses = preflight.check_pipeline(pipeline)
        missing = [s.name for s in statuses if not s.found]
        if not pipeline.requires_tools:
            self.preflight_label.setText("no external tools required")
        elif missing:
            self.preflight_label.setText(f"missing tools: {', '.join(missing)}")
        else:
            self.preflight_label.setText("all required tools present")

    def current_pipeline(self) -> Pipeline | None:
        if self.registry is None or not self.pipeline_combo.currentText():
            return None
        return self.registry.get(self.pipeline_combo.currentText())

    # -- page 2: acquisition ---------------------------------------------

    def _build_acquire_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.state_label = QLabel("not started")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.variant_list = QListWidget()

        buttons = QHBoxLayout()
        self.read_btn = QPushButton("Read")
        self.reread_btn = QPushButton("Re-read")
        self.best_btn = QPushButton("Mark best")
        self.fluxonly_btn = QPushButton("Keep flux only")
        self.read_btn.clicked.connect(lambda: self.start_acquire(best=True))
        self.reread_btn.clicked.connect(lambda: self.start_acquire(best=False))
        self.best_btn.clicked.connect(self._mark_best_selected)
        self.fluxonly_btn.clicked.connect(self._keep_flux_only)
        for b in (self.read_btn, self.reread_btn, self.best_btn, self.fluxonly_btn):
            buttons.addWidget(b)

        layout.addWidget(self.state_label)
        layout.addLayout(buttons)
        layout.addWidget(self.variant_list)
        layout.addWidget(self.log_view)
        return page

    def _ensure_session(self) -> DumpSession:
        if self.session is None:
            pipeline = self.current_pipeline()
            if pipeline is None:
                raise RemanenceError("no pipeline selected")
            run = create_run(self.staging_root)
            self.session = DumpSession(
                run, pipeline,
                captured_by=self.operator_edit.text() or "unknown",
                platform_hint=self.registry.get_format(pipeline.format).platform,
            )
        return self.session

    def start_acquire(self, *, best: bool, blocking: bool = False) -> None:
        session = self._ensure_session()
        params = self._collect_params(session.pipeline)
        device = self.device_edit.text() or None
        if blocking:
            runner = Runner(session.run, log=self._append_log)
            session.acquire(runner, params, device=device, best=best)
            self._on_acquired(True)
            return
        self._worker = AcquireWorker(session, params, device=device, best=best)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_acquired)
        self._worker.failed.connect(self._on_failed)
        self.read_btn.setEnabled(False)
        self.reread_btn.setEnabled(False)
        self._thread = run_in_thread(self._worker)

    def _collect_params(self, pipeline: Pipeline) -> dict:
        params: dict = {}
        for param in pipeline.parameters:
            if param.name == "revolutions":
                params["revolutions"] = self.revs_spin.value()
            elif param.default is not None:
                params[param.name] = param.default
        return params

    def _append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    def _on_acquired(self, success: bool) -> None:
        self.read_btn.setEnabled(True)
        self.reread_btn.setEnabled(True)
        self._refresh_variants()

    def _on_failed(self, message: str) -> None:
        self.read_btn.setEnabled(True)
        self.reread_btn.setEnabled(True)
        QMessageBox.warning(self, "Acquisition failed", message)

    def _refresh_variants(self) -> None:
        self.variant_list.clear()
        if self.session is None:
            return
        for v in self.session.flux:
            tag = " [best]" if v.best else ""
            quality = f" — {v.read_quality}" if v.read_quality else ""
            self.variant_list.addItem(f"variant {v.variant}: {v.temp_name}{tag}{quality}")
        verdict = self.session.assessment()
        self.state_label.setText(
            f"state: {verdict.state}  /  {verdict.preservation_level}  /  {verdict.decode_status}"
        )

    def _mark_best_selected(self) -> None:
        row = self.variant_list.currentRow()
        if self.session is not None and row >= 0:
            self.session.mark_best(self.session.flux.variants[row].variant)
            self._refresh_variants()

    def _keep_flux_only(self) -> None:
        if self.session is not None:
            self.session.discard_image()
            self.session.flux_stable = False
            self._refresh_variants()

    # -- page 3: photos ---------------------------------------------------

    def _build_photos_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.photo_type_combo = QComboBox()
        self.photo_type_combo.addItems(PHOTO_TYPES)
        self.keystone_check = QLineEdit()
        self.keystone_check.setPlaceholderText("media ratio for keystone (blank = none): 3.5 / 5.25 / 8")
        self.photo_list = QListWidget()
        import_btn = QPushButton("Import photo…")
        import_btn.clicked.connect(self._import_photo)
        layout.addWidget(QLabel("Type"))
        layout.addWidget(self.photo_type_combo)
        layout.addWidget(self.keystone_check)
        layout.addWidget(import_btn)
        layout.addWidget(self.photo_list)
        return page

    def _import_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import photo", "",
                                              "Images (*.jpg *.jpeg *.png)")
        if path:
            self.add_photo(path, self.photo_type_combo.currentText())

    def add_photo(self, path: str | Path, photo_type: str, ratio: str | None = None) -> None:
        session = self._ensure_session()
        ops = EditOps()
        ratio = ratio if ratio is not None else self.keystone_check.text().strip()
        # A real keystone needs four points from the UI; a bare ratio is ignored here.
        rel = session.add_photo(path, type=photo_type, ops=ops)
        self.photo_list.addItem(f"{photo_type}: {rel}")

    # -- page 4: metadata -------------------------------------------------

    def _build_metadata_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.operator_edit = QLineEdit()
        self.label_edit = QPlainTextEdit()
        self.media_edit = QLineEdit("5.25 DD")
        self.condition_edit = QLineEdit()
        layout.addRow("Operator", self.operator_edit)
        layout.addRow("Label text", self.label_edit)
        layout.addRow("Media", self.media_edit)
        layout.addRow("Condition", self.condition_edit)
        return page

    def _apply_metadata(self) -> None:
        if self.session is None:
            return
        label = self.label_edit.toPlainText().strip()
        if label:
            self.session.set_label_text(label)
        self.session.set_physical(
            media=self.media_edit.text() or None,
            condition=self.condition_edit.text() or None,
        )

    # -- page 5: summary --------------------------------------------------

    def _build_summary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.finish_btn = QPushButton("Write staging + manifest")
        self.finish_btn.clicked.connect(self.finalize)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.finish_btn)
        return page

    def _refresh_summary(self) -> None:
        if self.session is None:
            self.summary_label.setText("nothing acquired yet")
            return
        verdict = self.session.assessment()
        self.summary_label.setText(
            f"run: {self.session.run.run_id}\n"
            f"flux variants: {len(self.session.flux)}\n"
            f"image: {'yes' if self.session.image_temp_name else 'no'}\n"
            f"assessment: {verdict.state} / {verdict.preservation_level} / {verdict.decode_status}"
        )

    def finalize(self) -> str | None:
        if self.session is None:
            QMessageBox.warning(self, "Nothing to write", "Acquire a disk first.")
            return None
        self._apply_metadata()
        try:
            path = self.session.write_manifest()
        except RemanenceError as exc:
            QMessageBox.warning(self, "Cannot write manifest", str(exc))
            return None
        self.manifest_written.emit(str(path))
        QMessageBox.information(self, "Done", f"Wrote {path}")
        return str(path)

    # -- navigation -------------------------------------------------------

    def _go_next(self) -> None:
        index = self.stack.currentIndex()
        if index == self.stack.count() - 1:
            return
        if index == 3:
            self._apply_metadata()
        self.stack.setCurrentIndex(index + 1)
        if self.stack.currentIndex() == 4:
            self._refresh_summary()

    def _go_back(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))

    # -- settings / session lifecycle ------------------------------------

    def apply_settings(self, settings: Settings) -> None:
        """Re-read paths and acquisition defaults from settings, reload registry."""
        self.registry_path = settings.pipelines_path
        self.staging_root = settings.staging_root
        if settings.default_operator and not self.operator_edit.text():
            self.operator_edit.setText(settings.default_operator)
        if settings.default_device and not self.device_edit.text():
            self.device_edit.setText(settings.default_device)
        self.revs_spin.setValue(settings.default_revolutions)
        if settings.default_media_ratio and not self.keystone_check.text():
            self.keystone_check.setText(settings.default_media_ratio)
        self.load_registry(self.registry_path)

    def reset_session(self) -> None:
        """Discard the current session and return to the first step (new dump)."""
        self.session = None
        self.variant_list.clear()
        self.photo_list.clear()
        self.log_view.clear()
        self.state_label.setText("not started")
        self.stack.setCurrentIndex(0)

    def resume_run(self, run_path: str | Path) -> None:
        """Reopen an existing run to amend photos/metadata (SOFTWARE-SPEC.md §F9)."""
        if self.registry is None:
            raise RemanenceError("no pipelines registry loaded")
        self.session = load_session(run_path, self.registry)
        self._refresh_variants()
        self._refresh_summary()
        self.stack.setCurrentIndex(1)
