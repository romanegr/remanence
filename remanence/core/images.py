# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Non-destructive photo editing: keystone, rotate, crop, brightness/contrast.

Edits are recorded as a serialisable :class:`EditOps` value; the rectified image
is (re)generated from the original at export time, so the source is never mutated
(SOFTWARE-SPEC.md §F4, §5). The canonical pipeline is:

    keystone -> rotate -> crop -> brightness/contrast -> normalise/export.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# Real media aspect ratios (width / height) for the keystone target rectangle.
# Floppy jackets are close to square; 3.5" is very slightly taller than wide.
MEDIA_RATIOS = {
    "3.5": 90.0 / 94.0,
    "5.25": 1.0,
    "8": 1.0,
}

# Output normalisation defaults (SOFTWARE-SPEC.md §F4).
DEFAULT_MAX_LONG_EDGE = 2000
DEFAULT_JPEG_QUALITY = 80

Point = tuple[float, float]


@dataclass
class Keystone:
    # Four source corners in image pixels: top-left, top-right, bottom-right, bottom-left.
    points: list[Point]
    ratio: str = "5.25"


@dataclass
class Crop:
    # Pixel box on the (already keystone/rotation-corrected) image.
    left: int
    top: int
    right: int
    bottom: int


@dataclass
class EditOps:
    """Serialisable, non-destructive description of all edits applied to a photo."""

    keystone: Keystone | None = None
    rotation: float = 0.0          # degrees, counter-clockwise
    crop: Crop | None = None
    brightness: int = 0            # -100..100
    contrast: int = 0              # -100..100

    def to_dict(self) -> dict:
        data: dict = {}
        if self.keystone is not None:
            data["keystone"] = True
            data["ratio"] = self.keystone.ratio
        if self.rotation:
            data["rotation"] = self.rotation
        if self.crop is not None:
            data["crop"] = asdict(self.crop)
        if self.brightness:
            data["brightness"] = self.brightness
        if self.contrast:
            data["contrast"] = self.contrast
        return data


def load(path: str | Path) -> np.ndarray:
    """Load an image as a BGR ndarray (OpenCV convention)."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"could not load image: {path}")
    return image


def apply_keystone(image: np.ndarray, points: list[Point], ratio: str = "5.25") -> np.ndarray:
    """Rectify a four-corner perspective into a rectangle of the media's real ratio.

    ``points`` are ordered top-left, top-right, bottom-right, bottom-left.
    """
    if len(points) != 4:
        raise ValueError("keystone needs exactly four points")
    aspect = MEDIA_RATIOS.get(ratio)
    if aspect is None:
        raise ValueError(f"unknown media ratio: {ratio}")

    src = np.array(points, dtype=np.float32)
    # Output size: average the measured edge lengths, then honour the real ratio.
    width = (_dist(src[0], src[1]) + _dist(src[3], src[2])) / 2.0
    height = (_dist(src[0], src[3]) + _dist(src[1], src[2])) / 2.0
    out_w = int(round(max(width, height * aspect)))
    out_h = int(round(out_w / aspect))
    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, matrix, (out_w, out_h))


def rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    """Rotate counter-clockwise about the centre, expanding the canvas to fit."""
    if degrees % 360 == 0:
        return image
    h, w = image.shape[:2]
    centre = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(centre, degrees, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)
    matrix[0, 2] += (new_w / 2.0) - centre[0]
    matrix[1, 2] += (new_h / 2.0) - centre[1]
    return cv2.warpAffine(image, matrix, (new_w, new_h))


def crop(image: np.ndarray, box: Crop) -> np.ndarray:
    h, w = image.shape[:2]
    left = max(0, min(box.left, w))
    right = max(left, min(box.right, w))
    top = max(0, min(box.top, h))
    bottom = max(top, min(box.bottom, h))
    return image[top:bottom, left:right]


def adjust(image: np.ndarray, brightness: int = 0, contrast: int = 0) -> np.ndarray:
    """Apply brightness (-100..100) and contrast (-100..100)."""
    alpha = 1.0 + (contrast / 100.0)   # contrast gain
    beta = brightness * 255.0 / 100.0  # brightness offset
    return cv2.convertScaleAbs(image, alpha=alpha, beta=beta)


def render(image: np.ndarray, ops: EditOps) -> np.ndarray:
    """Apply all edits in canonical order, returning a new image."""
    result = image
    if ops.keystone is not None:
        result = apply_keystone(result, ops.keystone.points, ops.keystone.ratio)
    if ops.rotation:
        result = rotate(result, ops.rotation)
    if ops.crop is not None:
        result = crop(result, ops.crop)
    if ops.brightness or ops.contrast:
        result = adjust(result, ops.brightness, ops.contrast)
    return result


def export_normalized(
    source: str | Path,
    ops: EditOps,
    dest: str | Path,
    *,
    max_long_edge: int = DEFAULT_MAX_LONG_EDGE,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> Path:
    """Render ``source`` through ``ops`` and write a normalised JPEG to ``dest``.

    Output is JPEG (no EXIF), long edge capped at ``max_long_edge``. The source
    file is never modified.
    """
    image = render(load(source), ops)
    image = _downscale(image, max_long_edge)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # PIL.Image built from a raw array carries no EXIF metadata.
    Image.fromarray(rgb).save(dest, format="JPEG", quality=quality)
    return dest


def _downscale(image: np.ndarray, max_long_edge: int) -> np.ndarray:
    h, w = image.shape[:2]
    long_edge = max(h, w)
    if long_edge <= max_long_edge:
        return image
    scale = max_long_edge / long_edge
    return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))
