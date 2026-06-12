# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Background worker for acquisition, keeping heavy work off the UI thread.

The worker only calls :class:`remanence.core.session.DumpSession`; it carries no
business logic (SOFTWARE-SPEC.md §7 performance, CLAUDE.md §2).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from ..core.runner import Runner
from ..core.session import DumpSession


class AcquireWorker(QObject):
    """Runs one acquisition pass and emits its outcome."""

    log = Signal(str)
    finished = Signal(bool)   # success
    failed = Signal(str)

    def __init__(
        self,
        session: DumpSession,
        params: dict[str, Any],
        *,
        device: str | None = None,
        best: bool = False,
    ) -> None:
        super().__init__()
        self._session = session
        self._params = params
        self._device = device
        self._best = best

    def run(self) -> None:
        runner = Runner(self._session.run, log=self.log.emit)
        try:
            result = self._session.acquire(
                runner, self._params, device=self._device, best=self._best
            )
        except Exception as exc:  # noqa: BLE001 - surface to the UI
            self.failed.emit(str(exc))
            return
        self.finished.emit(result.success)


def run_in_thread(worker: AcquireWorker) -> QThread:
    """Move ``worker`` onto a new QThread and start it; returns the thread."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.start()
    return thread
