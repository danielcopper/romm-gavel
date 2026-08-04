"""Compile the native core and run the ladder vectors against its C ABI.

The vectors are the contract, so this harness answers one question: does the
compiled library produce ``expected`` for every one of them? It compiles
``core/gavel.c`` to a shared object with the compiler named by ``$CC`` (default
``cc``; may contain spaces, e.g. ``zig cc``), loads it via ctypes, and drives the
two public functions.

Conformance only: every ladder vector in ``vectors/ladder/*.json`` against
``gavel_resolve_upload_conflict``. Breadth over the whole input space belongs to
``exhaustive_driver.c``, which walks all 1296 combinations against its own
oracle under sanitizers — this harness proves the ABI answers the contract, not
that it agrees with some other implementation.
"""

from __future__ import annotations

import ctypes
import json
import os
import shlex
import subprocess
import tempfile
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


def _load_vectors() -> list[object]:
    files = sorted(_VECTOR_DIR.glob("*.json"))
    assert files, f"no vector files found in {_VECTOR_DIR}"
    params: list[object] = []
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
