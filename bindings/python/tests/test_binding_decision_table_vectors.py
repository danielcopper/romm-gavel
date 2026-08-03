"""Run every decision-table vector through the Python binding.

Same contract as the raw-ABI harness in ``core/tests``, one layer up: this
proves the *wrapper* — struct marshalling and ISO-8601 parsing included —
decides exactly like the contract, and stays in step with the Python reference
across a broad sweep of input shapes.

The sweep matters more here than for the ladder. The ladder's inputs are four
hashes and can be walked exhaustively; the decision table's are nested objects,
so the differential instead crosses the axes that actually branch: which
``device_syncs`` entry the head carries, whether timestamps parse, whether a
baseline exists, and whether the local file is present, empty, or shrunken.
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
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent
_CORE_DIR = _REPO_ROOT / "core"
_VECTOR_DIR = _REPO_ROOT / "vectors" / "decision-table"

_CFLAGS = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-fPIC", "-shared", "-O2"]

sys.path.insert(0, str(_REPO_ROOT / "bindings" / "python"))
from gavel_native import GavelCore  # noqa: E402

sys.path.remove(str(_REPO_ROOT / "bindings" / "python"))


def _build_core() -> GavelCore:
    """Compile the core with ``$CC`` and hand the library to the binding."""
    cc = shlex.split(os.environ.get("CC", "cc"))
    with tempfile.TemporaryDirectory(prefix="gavel-binding-table-") as tmpdir:
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
def test_binding_decision_table_vector(vector: dict[str, Any]):
    i = vector["input"]
    got = _CORE.compute_sync_action(
        i["local_file"],
        i["server_saves_in_slot"],
        i["files_state"],
        i["device_id"],
        i["local_hash"],
    )
    assert got == vector["expected"], vector.get("rationale", vector["name"])


def _load_reference():
    """Import the Python reference, adding then removing ``reference/`` from the path."""
    ref_path = str(_REPO_ROOT / "reference")
    sys.path.insert(0, ref_path)
    try:
        from gavel_reference import compute_sync_action
    finally:
        sys.path.remove(ref_path)
    return compute_sync_action


_DEVICE_ID = "device-a"
_HASHES = [None, "", "a" * 32, "b" * 32]
_TIMESTAMPS = ["2026-06-01T12:00:00Z", "2026-06-02T12:00:00Z", "garbage", None]

# Epochs around the second timestamp above (2026-06-02T12:00:00Z), so the
# fall-through path sees a local file that is older, exactly equal, and newer.
_EQUAL_MTIME = 1780401600.0

# Presence is what decides, not shape: a file the client could only partly stat
# still exists. The empty dict is in here on purpose — no vector can express it
# (the shape validator requires a filename), so this differential is the only
# thing pinning that ``{}`` reads as present rather than as absent.
_LOCAL_FILES = [
    None,
    {},
    {"filename": "game.srm"},
    {"filename": "game.srm", "size": 0, "mtime": _EQUAL_MTIME},
    {"filename": "game.srm", "size": 100, "mtime": _EQUAL_MTIME - 3600},
    {"filename": "game.srm", "size": 8192, "mtime": _EQUAL_MTIME},
    {"filename": "game.srm", "size": 8192, "mtime": _EQUAL_MTIME + 3600},
    # Not a size any filesystem reports, but it is what the shrink guard's
    # negative branch exists for.
    {"filename": "game.srm", "size": -1, "mtime": _EQUAL_MTIME},
]

_FILES_STATES = [
    {},
    {"last_sync_hash": "a" * 32},
    {"last_sync_hash": "a" * 32, "last_sync_server_hash": "b" * 32},
    {"last_sync_hash": "a" * 32, "last_sync_server_hash": "b" * 32, "last_sync_local_size": 8192},
    {"last_sync_hash": "", "last_sync_server_hash": ""},
    {"last_sync_hash": "b" * 32, "last_sync_local_size": 0},
]

_DEVICE_SYNC_SETS = [
    [],
    [{"device_id": _DEVICE_ID, "is_current": True}],
    [{"device_id": _DEVICE_ID, "is_current": False}],
    [{"device_id": "device-b", "is_current": True}],
    [{"device_id": "device-b", "is_current": True}, {"device_id": _DEVICE_ID, "is_current": False}],
]


def _slots() -> list[list[dict[str, Any]]]:
    """Representative server-save lists: empty, single, and two-save slots."""
    slots: list[list[dict[str, Any]]] = [[]]
    for updated_at, content_hash, syncs in product(_TIMESTAMPS, _HASHES, _DEVICE_SYNC_SETS):
        slots.append([{"id": 101, "updated_at": updated_at, "content_hash": content_hash, "device_syncs": syncs}])
    # Two saves so head selection itself is under test — newest wins, and an
    # unparseable timestamp loses regardless of list order.
    for first, second in product(_TIMESTAMPS, _TIMESTAMPS):
        slots.append(
            [
                {"id": 101, "updated_at": first, "content_hash": "a" * 32, "device_syncs": _DEVICE_SYNC_SETS[1]},
                {"id": 102, "updated_at": second, "content_hash": "b" * 32, "device_syncs": _DEVICE_SYNC_SETS[2]},
            ]
        )
    return slots


def test_binding_matches_python_reference_across_input_shapes():
    """Differential: the binding agrees with the reference on every crossed shape."""
    compute_ref = _load_reference()
    mismatches: list[object] = []
    checked = 0
    for local_file, slot, files_state, local_hash in product(_LOCAL_FILES, _slots(), _FILES_STATES, _HASHES):
        checked += 1
        got = _CORE.compute_sync_action(local_file, slot, files_state, _DEVICE_ID, local_hash)
        want = compute_ref(local_file, slot, files_state, _DEVICE_ID, local_hash)
        if got != want:
            mismatches.append((local_file, slot, files_state, local_hash, got, want))
    assert not mismatches, f"{len(mismatches)} of {checked} mismatched; first: {mismatches[0]}"
    # Guards against a fixture list silently collapsing — the sweep is ~18k, so
    # anything near this bound means an axis stopped contributing.
    assert checked > 15_000, f"differential shrank to {checked} combinations"


@pytest.mark.parametrize("field", ["local_file", "files_state"])
def test_a_non_integral_size_is_refused(field: str):
    """Sizes are whole bytes, and rounding one would land on the loaded value.

    The ABI carries a size as ``int64_t``. Quietly truncating 0.5 gives 0 —
    exactly what the corrupt-local guard reacts to — so an unrepresentable size
    raises rather than answering a different question. No vector can reach this
    (the shape validator requires an integer size), which is why it is pinned
    here.
    """
    local_file: dict[str, Any] = {"filename": "game.srm", "size": 8192, "mtime": _EQUAL_MTIME}
    files_state: dict[str, Any] = {}
    if field == "local_file":
        local_file["size"] = 1.5
    else:
        files_state["last_sync_local_size"] = 1.5

    with pytest.raises(ValueError, match="whole number of bytes"):
        _CORE.compute_sync_action(local_file, [], files_state, _DEVICE_ID, "a" * 32)
