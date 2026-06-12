# remanence — floppy disk acquisition (Dump) and catalogue (Library) tool
# Copyright (C) 2026 Romain Negrel
# Distributed under the terms of the CeCILL-2.1 license; see LICENSE at the
# repository root for the full text.
# SPDX-License-Identifier: CeCILL-2.1
"""sha256 helper tests."""

from __future__ import annotations

import hashlib

from remanence.core.hashing import sha256_bytes, sha256_file

# Known-answer test vector: sha256 of the empty input.
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_bytes_empty():
    assert sha256_bytes(b"") == EMPTY_SHA


def test_sha256_bytes_known_vector():
    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_sha256_file_matches_bytes(tmp_path):
    payload = b"remanence flux capture" * 100_000  # exercises chunked reads
    target = tmp_path / "flux.scp"
    target.write_bytes(payload)
    assert sha256_file(target) == sha256_bytes(payload)


def test_sha256_file_empty(tmp_path):
    target = tmp_path / "empty.bin"
    target.write_bytes(b"")
    assert sha256_file(target) == EMPTY_SHA
