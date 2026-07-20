"""Compile the native core and run the ladder vectors + a differential cross-check.

The C library must be behaviorally identical to the Python reference and pass the
same conformance vectors. This harness compiles ``core/gavel.c`` to a shared
object with the compiler named by ``$CC`` (default ``cc``; may contain spaces,
e.g. ``zig cc``), loads it via ctypes, and drives the two public functions.

Two tiers:
  - every ladder vector in ``vectors/ladder/*.json`` against
    ``gavel_resolve_upload_conflict`` — the normative conformance run;
  - a differential over all 1296 canonical hash combinations against the Python
    reference, so the C port and the reference can never silently drift.
"""

from __future__ import annotations

import ctypes
import json
import os
import shlex
import subprocess
import sys
import tempfile
from itertools import product
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_CORE_DIR = _HERE.parent
_REPO_ROOT = _CORE_DIR.parent
_VECTOR_DIR = _REPO_ROOT / "vectors" / "ladder"

_CFLAGS = [
    "-std=c99",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-pedantic",
    "-fPIC",
    "-shared",
    "-O2",
]

_RESOLUTION = {0: "download", 1: "conflict"}

# Canonical inputs for the differential: unknown (NULL), empty, and four
# distinct 32-char hashes — the same alphabet the exhaustive C driver walks.
_ALPHABET = [None, "", "a" * 32, "b" * 32, "c" * 32, "d" * 32]


def _compile_lib() -> ctypes.CDLL:
    """Compile the core to a shared object with ``$CC`` and load it via ctypes."""
    cc = shlex.split(os.environ.get("CC", "cc"))
    with tempfile.TemporaryDirectory(prefix="gavel-core-") as tmpdir:
        so_path = Path(tmpdir) / "libgavel.so"
        cmd = [*cc, *_CFLAGS, str(_CORE_DIR / "gavel.c"), "-o", str(so_path)]
        subprocess.run(cmd, check=True)
        # Loading inside the with-block is fine: on Linux the mapping keeps the
        # ELF alive after the file is deleted, so nothing leaks into /tmp.
        lib = ctypes.CDLL(str(so_path))
    lib.gavel_resolve_upload_conflict.argtypes = [ctypes.c_char_p] * 4
    lib.gavel_resolve_upload_conflict.restype = ctypes.c_int
    lib.gavel_local_matches_server.argtypes = [ctypes.c_char_p] * 4
    lib.gavel_local_matches_server.restype = ctypes.c_int
    return lib


_LIB = _compile_lib()


def _encode(value: str | None) -> bytes | None:
    """Map a JSON hash value to a ctypes arg: None → NULL, "" → b"", else utf-8."""
    if value is None:
        return None
    return value.encode("utf-8")


def _load_vectors() -> list:
    files = sorted(_VECTOR_DIR.glob("*.json"))
    assert files, f"no vector files found in {_VECTOR_DIR}"
    params = []
    for path in files:
        data = json.loads(path.read_text())
        for vector in data["vectors"]:
            params.append(pytest.param(vector, id=f"{path.stem}:{vector['name']}"))
    return params


@pytest.mark.parametrize("vector", _load_vectors())
def test_ladder_vector(vector):
    i = vector["input"]
    got = _LIB.gavel_resolve_upload_conflict(
        _encode(i["local_hash"]),
        _encode(i["last_sync_hash"]),
        _encode(i["server_content_hash"]),
        _encode(i["last_sync_server_hash"]),
    )
    assert _RESOLUTION[got] == vector["expected"], vector.get("rationale", vector["name"])


def _load_reference():
    """Import the Python reference, adding then removing ``reference/`` from the path."""
    ref_path = str(_REPO_ROOT / "reference")
    sys.path.insert(0, ref_path)
    try:
        from gavel_reference import local_matches_server, resolve_upload_conflict
    finally:
        sys.path.remove(ref_path)
    return resolve_upload_conflict, local_matches_server


def test_c_matches_python_reference_exhaustively():
    """Differential: the C port agrees with the Python reference on all 1296 combos."""
    resolve_ref, matches_ref = _load_reference()
    mismatches = []
    for local, last_sync, server, last_sync_server in product(_ALPHABET, repeat=4):
        # Ladder — arg order (local, last_sync, server, last_sync_server).
        c_resolve = _RESOLUTION[
            _LIB.gavel_resolve_upload_conflict(
                _encode(local), _encode(last_sync), _encode(server), _encode(last_sync_server)
            )
        ]
        py_resolve = resolve_ref(local, last_sync, server, last_sync_server)
        if c_resolve != py_resolve:
            mismatches.append(("resolve", (local, last_sync, server, last_sync_server), c_resolve, py_resolve))

        # Matcher — arg order (local, server, last_sync, last_sync_server).
        c_match = bool(
            _LIB.gavel_local_matches_server(
                _encode(local), _encode(server), _encode(last_sync), _encode(last_sync_server)
            )
        )
        py_match = matches_ref(local, server, last_sync, last_sync_server)
        if c_match != py_match:
            mismatches.append(("matches", (local, server, last_sync, last_sync_server), c_match, py_match))

    assert not mismatches, f"{len(mismatches)} mismatch(es); first: {mismatches[0]}"
