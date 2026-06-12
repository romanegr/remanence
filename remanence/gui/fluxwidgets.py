# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Flux visualisation widgets (SOFTWARE-SPEC.md §F11).

Thin renderers over :mod:`remanence.core.fluxview` output: a flux-interval
histogram and a track density map. No parsing or analysis happens here.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class HistogramWidget(QWidget):
    """Bar chart of the flux-interval histogram."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._counts = np.zeros(0, dtype=np.int64)
        self.setMinimumHeight(120)

    def set_histogram(self, counts: np.ndarray) -> None:
        self._counts = np.asarray(counts)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 24))
        if self._counts.size == 0 or self._counts.max() == 0:
            return
        w, h = self.width(), self.height()
        n = self._counts.size
        peak = float(self._counts.max())
        bar_w = max(1.0, w / n)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(120, 200, 255))
        for i, value in enumerate(self._counts):
            bar_h = (value / peak) * (h - 4)
            painter.drawRect(int(i * bar_w), int(h - bar_h), int(bar_w) or 1, int(bar_h))


class TrackMapWidget(QWidget):
    """Grayscale image of the track × angular-position density map."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self.setMinimumHeight(120)

    def set_track_map(self, grid: np.ndarray) -> None:
        self._pixmap = self._grid_to_pixmap(grid)
        self.update()

    @staticmethod
    def _grid_to_pixmap(grid: np.ndarray) -> QPixmap | None:
        if grid.size == 0:
            return None
        peak = float(grid.max()) or 1.0
        norm = np.ascontiguousarray((grid / peak * 255).astype(np.uint8))
        rows, cols = norm.shape
        image = QImage(norm.data, cols, rows, cols, QImage.Format_Grayscale8)
        return QPixmap.fromImage(image.copy())

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 24))
        if self._pixmap is not None:
            scaled = self._pixmap.scaled(
                self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(0, 0, scaled)
