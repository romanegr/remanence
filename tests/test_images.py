# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Image editing tests: keystone correction (non-destructive), export, adjust."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from remanence.core import images
from remanence.core.images import Crop, EditOps, Keystone


def _skewed_white_quad(size=400):
    """Black canvas with a white trapezoid (a square 'photographed' at an angle)."""
    img = np.zeros((size, size, 3), dtype=np.uint8)
    # Top edge narrower than bottom edge -> perspective skew.
    quad = np.array([[120, 60], [300, 90], [360, 340], [60, 320]], dtype=np.int32)
    cv2.fillConvexPoly(img, quad, (255, 255, 255))
    points = [(120, 60), (300, 90), (360, 340), (60, 320)]
    return img, points


def test_keystone_rectifies_skewed_quad():
    img, points = _skewed_white_quad()
    out = images.apply_keystone(img, points, ratio="5.25")
    h, w = out.shape[:2]
    # A correct homography maps the quad to fill the whole output rectangle:
    # all four corners should now be white.
    for (y, x) in [(2, 2), (2, w - 3), (h - 3, 2), (h - 3, w - 3)]:
        assert out[y, x].mean() > 200, f"corner ({y},{x}) not white"
    # And the frame is overwhelmingly white (quad fills it).
    assert out.mean() > 230
    # Square media -> near-square output.
    assert abs(w - h) <= 2


def test_keystone_requires_four_points():
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        images.apply_keystone(img, [(0, 0), (1, 1)], ratio="5.25")


def test_keystone_is_non_destructive(tmp_path):
    img, points = _skewed_white_quad()
    src = tmp_path / "front.png"
    cv2.imwrite(str(src), img)
    before = src.read_bytes()

    ops = EditOps(keystone=Keystone(points=points, ratio="5.25"))
    dest = images.export_normalized(src, ops, tmp_path / "out.jpg")

    assert dest.exists()
    # Source file untouched.
    assert src.read_bytes() == before
    assert ops.to_dict()["keystone"] is True
    assert ops.to_dict()["ratio"] == "5.25"


def test_export_downscales_long_edge(tmp_path):
    big = np.full((3000, 1500, 3), 128, dtype=np.uint8)
    src = tmp_path / "big.png"
    cv2.imwrite(str(src), big)
    dest = images.export_normalized(src, EditOps(), tmp_path / "small.jpg", max_long_edge=2000)
    out = cv2.imread(str(dest))
    assert max(out.shape[:2]) == 2000


def test_adjust_brightness_increases_mean():
    img = np.full((20, 20, 3), 100, dtype=np.uint8)
    brighter = images.adjust(img, brightness=20, contrast=0)
    assert brighter.mean() > img.mean()


def test_render_applies_crop():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    ops = EditOps(crop=Crop(left=10, top=10, right=60, bottom=40))
    out = images.render(img, ops)
    assert out.shape[:2] == (30, 50)
