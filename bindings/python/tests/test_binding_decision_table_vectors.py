"""Run every decision-table vector through the Python binding.

Same contract as the raw-ABI harness in ``core/tests``, one layer up: this proves
the *wrapper* — struct marshalling and ISO-8601 parsing included — answers every
vector the way the contract says.

Alongside them sit tests for the input shapes no vector can express, because the
shape validator rejects them: a local file object with no fields, a server save
with no ``device_syncs`` key, a size that is not a whole number. Those are the
marshalling decisions this layer owns, and nothing else would catch them.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
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


_DEVICE = "device-a"
_HEAD_UPDATED_AT = "2026-06-02T12:00:00Z"
_HEAD_EPOCH = 1780401600.0
_HASH = "a" * 32


def test_an_empty_local_file_object_is_a_present_file():
    """Presence is the pointer, never the fields.

    An object the client could not measure still means the file is there. The
    shape validator requires a filename, so no vector can carry this — but a
    binding that decided presence from the fields rather than from whether it
    passes NULL would answer the opposite here.
    """
    assert _CORE.compute_sync_action({}, [], {}, _DEVICE, None) == {"action": "upload", "target_save_id": None}
    assert _CORE.compute_sync_action(None, [], {}, _DEVICE, None) == {
        "action": "skip",
        "reason": "nothing_to_sync",
        "adopt_baseline": False,
    }


def test_a_save_without_a_device_syncs_key_has_no_entries():
    """An absent array is an empty one, not a NULL pointer with a stale count.

    Vectors always carry ``device_syncs`` — the shape validator requires a list
    — so only this can pin what happens when the key is missing entirely. The
    core reads pointer plus count, and a count left over from a sibling save
    would read freed memory rather than decide the no-entry branch.
    """
    save = {"id": 101, "updated_at": _HEAD_UPDATED_AT, "content_hash": "c" * 32}
    assert _CORE.compute_sync_action(None, [save], {}, _DEVICE, None) == {
        "action": "download",
        "server_save_id": 101,
    }


def test_a_local_mtime_is_compared_against_the_parsed_head():
    """The ISO string has to become the same instant the mtime is measured in.

    A binding that parsed the head as local time rather than UTC would shift it
    by hours, and the at-or-after comparison on the fall-through path would flip
    for an mtime this close to it.
    """
    equal = _CORE.compute_sync_action(
        {"filename": "game.srm", "size": 8192, "mtime": _HEAD_EPOCH},
        [{"id": 101, "updated_at": _HEAD_UPDATED_AT, "content_hash": "c" * 32, "device_syncs": []}],
        {"last_sync_hash": _HASH},
        _DEVICE,
        _HASH,
    )
    assert equal == {"action": "upload", "target_save_id": None}

    older = _CORE.compute_sync_action(
        {"filename": "game.srm", "size": 8192, "mtime": _HEAD_EPOCH - 1},
        [{"id": 101, "updated_at": _HEAD_UPDATED_AT, "content_hash": "c" * 32, "device_syncs": []}],
        {"last_sync_hash": _HASH},
        _DEVICE,
        _HASH,
    )
    assert older == {"action": "download", "server_save_id": 101}


def test_the_device_entry_is_found_in_a_multi_entry_array():
    """Arrays go in as pointer plus count; an off-by-one would read the wrong one."""
    save = {
        "id": 101,
        "updated_at": _HEAD_UPDATED_AT,
        "content_hash": "c" * 32,
        "device_syncs": [
            {"device_id": "device-b", "is_current": True},
            {"device_id": "device-c", "is_current": True},
            {"device_id": _DEVICE, "is_current": False},
        ],
    }
    # is_current=false for this device and no local file: download the head.
    assert _CORE.compute_sync_action(None, [save], {}, _DEVICE, None) == {
        "action": "download",
        "server_save_id": 101,
    }


@pytest.mark.parametrize("field", ["local_file", "files_state"])
def test_a_non_integral_size_is_refused(field: str):
    """Sizes are whole bytes, and rounding one would land on the loaded value.

    The ABI carries a size as ``int64_t``. Quietly truncating 0.5 gives 0 —
    exactly what the corrupt-local guard reacts to — so an unrepresentable size
    raises rather than answering a different question. No vector can reach this
    (the shape validator requires an integer size), which is why it is pinned
    here.
    """
    local_file: dict[str, Any] = {"filename": "game.srm", "size": 8192, "mtime": _HEAD_EPOCH}
    files_state: dict[str, Any] = {}
    if field == "local_file":
        local_file["size"] = 1.5
    else:
        files_state["last_sync_local_size"] = 1.5

    with pytest.raises(ValueError, match="whole number of bytes"):
        _CORE.compute_sync_action(local_file, [], files_state, _DEVICE, _HASH)
