"""Run every ladder vector through the Python binding.

Same contract as the raw-ABI harness in ``core/tests``, one layer up: this
proves the *wrapper* — value conversion at the FFI boundary included — decides
exactly like the contract, and stays byte-for-byte in step with the Python
reference across all canonical input combinations.
"""

from __future__ import annotations

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
_REPO_ROOT = _HERE.parent.parent.parent
_CORE_DIR = _REPO_ROOT / "core"
_VECTOR_DIR = _REPO_ROOT / "vectors" / "ladder"

_CFLAGS = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-fPIC", "-shared", "-O2"]

# Canonical inputs for the differential: unknown (NULL), empty, and four
# distinct 32-char hashes — the alphabet the other harnesses walk too.
_ALPHABET = [None, "", "a" * 32, "b" * 32, "c" * 32, "d" * 32]

sys.path.insert(0, str(_REPO_ROOT / "bindings" / "python"))
from gavel_native import GavelCore  # noqa: E402

sys.path.remove(str(_REPO_ROOT / "bindings" / "python"))


def _build_core() -> GavelCore:
    """Compile the core with ``$CC`` and hand the library to the binding."""
    cc = shlex.split(os.environ.get("CC", "cc"))
    with tempfile.TemporaryDirectory(prefix="gavel-binding-") as tmpdir:
        so_path = Path(tmpdir) / "libgavel.so"
        subprocess.run([*cc, *_CFLAGS, str(_CORE_DIR / "gavel.c"), "-o", str(so_path)], check=True)
        # Loading inside the with-block is fine: on Linux the mapping keeps the
        # ELF alive after the file is deleted, so nothing leaks into /tmp.
        return GavelCore(so_path)


_CORE = _build_core()


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
def test_binding_ladder_vector(vector):
    i = vector["input"]
    got = _CORE.resolve_upload_conflict(
        i["local_hash"],
        i["last_sync_hash"],
        i["server_content_hash"],
        i["last_sync_server_hash"],
    )
    assert got == vector["expected"], vector.get("rationale", vector["name"])


def _load_reference():
    """Import the Python reference, adding then removing ``reference/`` from the path."""
    ref_path = str(_REPO_ROOT / "reference")
    sys.path.insert(0, ref_path)
    try:
        from gavel_reference import local_matches_server, resolve_upload_conflict
    finally:
        sys.path.remove(ref_path)
    return resolve_upload_conflict, local_matches_server


def test_binding_matches_python_reference_exhaustively():
    """Differential: the binding agrees with the reference on all 1296 combos."""
    resolve_ref, matches_ref = _load_reference()
    mismatches = []
    for combo in product(_ALPHABET, repeat=4):
        local, last_sync, server, last_sync_server = combo
        if _CORE.resolve_upload_conflict(local, last_sync, server, last_sync_server) != resolve_ref(
            local, last_sync, server, last_sync_server
        ):
            mismatches.append(("resolve_upload_conflict", combo))
        if _CORE.local_matches_server(local, server, last_sync, last_sync_server) != matches_ref(
            local, server, last_sync, last_sync_server
        ):
            mismatches.append(("local_matches_server", combo))
    assert not mismatches, mismatches[:5]
