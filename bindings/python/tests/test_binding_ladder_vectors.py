"""Run every ladder vector through the Python binding.

Same contract as the raw-ABI harness in ``core/tests``, one layer up: this proves
the *wrapper* — value conversion at the FFI boundary included — answers every
vector the way the contract says. It deliberately compares against nothing but
the vectors; the reference is another implementation, not the standard.

Library selection matches those harnesses: ``$CC`` compiles the core, or
``$GAVEL_LIBRARY`` names an already-built ``.so`` to hand the binding instead.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent
_CORE_DIR = _REPO_ROOT / "core"
_VECTOR_DIR = _REPO_ROOT / "vectors" / "ladder"

_CFLAGS = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-fPIC", "-shared", "-O2"]

sys.path.insert(0, str(_REPO_ROOT / "bindings" / "python"))
from gavel_native import GavelCore  # noqa: E402

sys.path.remove(str(_REPO_ROOT / "bindings" / "python"))


def _load_core() -> GavelCore:
    """Hand the binding the library under test, compiling one when none is supplied."""
    prebuilt = os.environ.get("GAVEL_LIBRARY")
    if prebuilt:
        # Resolved to absolute: dlopen reads a name without a slash as a library
        # to search for on the system paths, not as a file next to the caller.
        path = Path(prebuilt).resolve()
        # Never a fall back to compiling. The caller believes it is judging that
        # artifact, and a silent recompile would hand back a pass for bytes
        # nothing ever ran.
        if not path.is_file():
            raise FileNotFoundError(f"GAVEL_LIBRARY points at {path}, which is not a file")
        return GavelCore(path)
    cc = shlex.split(os.environ.get("CC", "cc"))
    with tempfile.TemporaryDirectory(prefix="gavel-binding-") as tmpdir:
        so_path = Path(tmpdir) / "libgavel.so"
        subprocess.run([*cc, *_CFLAGS, str(_CORE_DIR / "gavel.c"), "-o", str(so_path)], check=True)
        # Loading inside the with-block is fine: on Linux the mapping keeps the
        # ELF alive after the file is deleted, so nothing leaks into /tmp.
        return GavelCore(so_path)


_CORE = _load_core()


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
