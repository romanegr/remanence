# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""Flux variant and disk-assessment tests (SOFTWARE-SPEC.md §F3)."""

from __future__ import annotations

import pytest

from remanence.core.errors import RemanenceError
from remanence.core.flux import (
    STATE_DECODED,
    STATE_FLUX_ONLY,
    STATE_UNSTABLE,
    FluxSet,
    assess_disk,
)

ZERO = "0" * 64


def test_variants_are_numbered_sequentially():
    fs = FluxSet()
    a = fs.add("flux_read01.scp", ZERO)
    b = fs.add("flux_read02.scp", ZERO, read_quality="9 weak sectors")
    assert (a.variant, b.variant) == (1, 2)
    assert len(fs) == 2


def test_mark_best_is_exclusive():
    fs = FluxSet()
    fs.add("a.scp", ZERO)
    fs.add("b.scp", ZERO)
    fs.add("c.scp", ZERO)
    fs.mark_best(2)
    assert fs.best().variant == 2
    fs.mark_best(3)
    assert fs.best().variant == 3
    assert sum(1 for v in fs if v.best) == 1


def test_add_best_sets_flag():
    fs = FluxSet()
    fs.add("a.scp", ZERO)
    fs.add("b.scp", ZERO, best=True)
    assert fs.best().temp_name == "b.scp"


def test_remove_variant():
    fs = FluxSet()
    fs.add("a.scp", ZERO)
    fs.add("b.scp", ZERO)
    fs.remove(1)
    assert [v.temp_name for v in fs] == ["b.scp"]


def test_mark_best_unknown_raises():
    fs = FluxSet()
    with pytest.raises(RemanenceError):
        fs.mark_best(99)


def test_assess_healthy_disk_is_gold_and_decoded():
    a = assess_disk(has_flux=True, has_image=True, decode_attempted=True, decode_succeeded=True)
    assert a.preservation_level == "gold"
    assert a.decode_status == "ok"
    assert a.needs_redecode is False
    assert a.state == STATE_DECODED


def test_assess_flux_only_is_silver_and_needs_redecode():
    a = assess_disk(has_flux=True, has_image=False, decode_attempted=True,
                    decode_succeeded=False, flux_stable=True)
    assert a.preservation_level == "silver"
    assert a.decode_status == "failed"
    assert a.needs_redecode is True
    assert a.state == STATE_FLUX_ONLY


def test_assess_unstable_disk_state():
    a = assess_disk(has_flux=True, has_image=False, decode_attempted=True,
                    decode_succeeded=False, flux_stable=False)
    assert a.state == STATE_UNSTABLE


def test_assess_partial_capture_is_bronze():
    a = assess_disk(has_flux=True, has_image=False, decode_attempted=False,
                    decode_succeeded=False, capture_partial=True)
    assert a.preservation_level == "bronze"
    assert a.decode_status == "not_attempted"


def test_assess_image_only_is_bronze():
    a = assess_disk(has_flux=False, has_image=True, decode_attempted=True,
                    decode_succeeded=True)
    assert a.preservation_level == "bronze"
