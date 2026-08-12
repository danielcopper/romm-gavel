"""Compile the native core and run the decision-table vectors against the raw ABI.

The counterpart to ``test_core_ladder_vectors.py`` for the full sync decision.
Marshalling here is deliberately written from scratch rather than reused from
``bindings/python`` — this harness proves the *C ABI*, so it has to be
independent of the wrapper that is itself under test one layer up. It doubles as
a worked example of calling ``gavel_compute_sync_action`` from nothing but the
header: build the structs, pass pointer + count for each array, read the tagged
result back out.

Library selection matches the ladder harness: ``$CC`` compiles the core, or
``$GAVEL_LIBRARY`` names an already-built ``.so`` to judge instead.
"""

from __future__ import annotations

import ctypes
import json
import os
import shlex
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent
_CORE_DIR = _HERE.parent
_REPO_ROOT = _CORE_DIR.parent
_VECTOR_DIR = _REPO_ROOT / "vectors" / "decision-table"

_CFLAGS = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-fPIC", "-shared", "-O2"]

_ACTIONS = {0: "skip", 1: "upload", 2: "download", 3: "conflict"}
_SKIP_REASONS = {0: "synced", 1: "nothing_to_sync"}


class DeviceSync(ctypes.Structure):
    _fields_ = (("device_id", ctypes.c_char_p), ("is_current", ctypes.c_int))


class ServerSave(ctypes.Structure):
    _fields_ = (
        ("id", ctypes.c_int64),
        ("updated_at_epoch", ctypes.c_double),
        ("has_updated_at", ctypes.c_int),
        ("content_hash", ctypes.c_char_p),
        ("device_syncs", ctypes.POINTER(DeviceSync)),
        ("device_sync_count", ctypes.c_size_t),
    )


class LocalFile(ctypes.Structure):
    _fields_ = (
        ("size", ctypes.c_int64),
        ("has_size", ctypes.c_int),
        ("mtime", ctypes.c_double),
        ("has_mtime", ctypes.c_int),
    )


class Bookkeeping(ctypes.Structure):
    _fields_ = (
        ("last_sync_hash", ctypes.c_char_p),
        ("last_sync_server_hash", ctypes.c_char_p),
        ("last_sync_local_size", ctypes.c_int64),
        ("has_last_sync_local_size", ctypes.c_int),
    )


class SyncAction(ctypes.Structure):
    _fields_ = (
        ("action", ctypes.c_int),
        ("reason", ctypes.c_int),
        ("adopt_baseline", ctypes.c_int),
        ("target_save_id", ctypes.c_int64),
        ("has_target_save_id", ctypes.c_int),
        ("server_save_id", ctypes.c_int64),
    )


def _load_lib() -> ctypes.CDLL:
    """Load the library under test, compiling the core when none is supplied."""
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
        lib = ctypes.CDLL(str(path))
    else:
        cc = shlex.split(os.environ.get("CC", "cc"))
        with tempfile.TemporaryDirectory(prefix="gavel-core-table-") as tmpdir:
            so_path = Path(tmpdir) / "libgavel.so"
            subprocess.run([*cc, *_CFLAGS, str(_CORE_DIR / "gavel.c"), "-o", str(so_path)], check=True)
            # Loading inside the with-block is fine: on Linux the mapping keeps
            # the ELF alive after the file is deleted, so nothing leaks in /tmp.
            lib = ctypes.CDLL(str(so_path))
    lib.gavel_compute_sync_action.argtypes = [
        ctypes.POINTER(LocalFile),
        ctypes.POINTER(ServerSave),
        ctypes.c_size_t,
        ctypes.POINTER(Bookkeeping),
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.POINTER(SyncAction),
    ]
    lib.gavel_compute_sync_action.restype = None
    return lib


_LIB = _load_lib()


def _encode(value: str | None) -> bytes | None:
    """Map a JSON string value to a ctypes arg: None → NULL, "" → b"", else utf-8."""
    return None if value is None else value.encode("utf-8")


def _iso_to_epoch(value: str | None) -> float | None:
    """ISO-8601 → epoch seconds, or None when it does not parse.

    Timestamp parsing is the caller's job under this ABI; the core takes epoch
    seconds plus a "known" flag. The vectors always carry an explicit UTC
    offset, so this stays environment-independent.
    """
    if not value:
        return None
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def call_core(inputs: dict[str, Any]) -> dict[str, Any]:
    """Drive ``gavel_compute_sync_action`` with a decision-table vector's input."""
    keepalive: list[object] = []

    local_file = inputs["local_file"]
    c_local_file = None
    if local_file is not None:
        size = local_file.get("size")
        mtime = local_file.get("mtime")
        c_local_file = ctypes.pointer(
            LocalFile(
                size=int(size) if size is not None else 0,
                has_size=int(size is not None),
                mtime=float(mtime) if mtime is not None else 0.0,
                has_mtime=int(mtime is not None),
            )
        )

    server_saves = inputs["server_saves_in_slot"]
    c_saves = None
    if server_saves:
        c_saves = (ServerSave * len(server_saves))()
        keepalive.append(c_saves)
        for index, save in enumerate(server_saves):
            syncs = save.get("device_syncs") or []
            c_syncs = (DeviceSync * len(syncs))()
            keepalive.append(c_syncs)
            for sync_index, sync in enumerate(syncs):
                device_id = _encode(sync.get("device_id"))
                keepalive.append(device_id)
                c_syncs[sync_index].device_id = device_id
                c_syncs[sync_index].is_current = int(bool(sync.get("is_current")))

            content_hash = _encode(save.get("content_hash"))
            keepalive.append(content_hash)
            epoch = _iso_to_epoch(save.get("updated_at"))
            c_saves[index].id = save["id"]
            c_saves[index].updated_at_epoch = 0.0 if epoch is None else epoch
            c_saves[index].has_updated_at = int(epoch is not None)
            c_saves[index].content_hash = content_hash
            c_saves[index].device_syncs = ctypes.cast(c_syncs, ctypes.POINTER(DeviceSync))
            c_saves[index].device_sync_count = len(syncs)

    files_state = inputs["files_state"]
    recorded_size = files_state.get("last_sync_local_size")
    last_sync_hash = _encode(files_state.get("last_sync_hash"))
    last_sync_server_hash = _encode(files_state.get("last_sync_server_hash"))
    keepalive += [last_sync_hash, last_sync_server_hash]
    c_bookkeeping = ctypes.pointer(
        Bookkeeping(
            last_sync_hash=last_sync_hash,
            last_sync_server_hash=last_sync_server_hash,
            last_sync_local_size=int(recorded_size) if recorded_size is not None else 0,
            has_last_sync_local_size=int(recorded_size is not None),
        )
    )

    device_id = _encode(inputs["device_id"])
    local_hash = _encode(inputs["local_hash"])

    result = SyncAction()
    _LIB.gavel_compute_sync_action(
        c_local_file,
        c_saves,
        len(server_saves),
        c_bookkeeping,
        device_id,
        local_hash,
        ctypes.byref(result),
    )

    action = _ACTIONS[result.action]
    if action == "skip":
        return {"action": action, "reason": _SKIP_REASONS[result.reason], "adopt_baseline": bool(result.adopt_baseline)}
    if action == "upload":
        return {"action": action, "target_save_id": result.target_save_id if result.has_target_save_id else None}
    return {"action": action, "server_save_id": result.server_save_id}


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
def test_decision_table_vector(vector: dict[str, Any]):
    got = call_core(vector["input"])
    assert got == vector["expected"], vector.get("rationale", vector["name"])


def test_null_bookkeeping_decides_like_an_empty_record():
    """A NULL bookkeeping pointer is the raw-ABI spelling of "no record held".

    Bindings pass a struct of unknowns instead, so this path has no vector
    coverage — but it is part of the published ABI and must agree.
    """
    saves = (ServerSave * 1)()
    syncs = (DeviceSync * 1)()
    syncs[0].device_id = b"device-a"
    syncs[0].is_current = 1
    saves[0].id = 101
    saves[0].updated_at_epoch = 1780401600.0
    saves[0].has_updated_at = 1
    saves[0].content_hash = b"c" * 32
    saves[0].device_syncs = ctypes.cast(syncs, ctypes.POINTER(DeviceSync))
    saves[0].device_sync_count = 1
    local_file = ctypes.pointer(LocalFile(size=8192, has_size=1, mtime=1780401600.0, has_mtime=1))

    with_null = SyncAction()
    _LIB.gavel_compute_sync_action(
        local_file, saves, 1, None, b"device-a", b"a" * 32, ctypes.byref(with_null)
    )
    with_empty = SyncAction()
    _LIB.gavel_compute_sync_action(
        local_file,
        saves,
        1,
        ctypes.pointer(Bookkeeping(last_sync_hash=None, last_sync_server_hash=None, last_sync_local_size=0,
                                   has_last_sync_local_size=0)),
        b"device-a",
        b"a" * 32,
        ctypes.byref(with_empty),
    )

    assert with_null.action == with_empty.action == 0  # skip
    assert with_null.adopt_baseline == with_empty.adopt_baseline == 1


@pytest.mark.parametrize(
    ("device_id", "expected_action"),
    [(None, 0), (b"device-a", 3)],  # matches the NULL entry → skip; no match → conflict
)
def test_absent_device_ids_match_each_other(device_id: bytes | None, expected_action: int):
    """Device ids compare for plain equality, so two absent ids are the same id.

    That mirrors the reference, where a missing ``device_id`` key on both sides
    is ``None == None``. It is deliberately *not* the hash rule, where an
    unknown value proves nothing — and no vector can express a NULL device id,
    so this is the only thing pinning the distinction.
    """
    syncs = (DeviceSync * 1)()
    syncs[0].device_id = None
    syncs[0].is_current = 1
    saves = (ServerSave * 1)()
    saves[0].id = 101
    saves[0].updated_at_epoch = 1780401600.0
    saves[0].has_updated_at = 1
    saves[0].content_hash = b"c" * 32
    saves[0].device_syncs = ctypes.cast(syncs, ctypes.POINTER(DeviceSync))
    saves[0].device_sync_count = 1
    local_file = ctypes.pointer(LocalFile(size=8192, has_size=1, mtime=1780401600.0, has_mtime=1))

    result = SyncAction()
    _LIB.gavel_compute_sync_action(local_file, saves, 1, None, device_id, b"a" * 32, ctypes.byref(result))
    assert result.action == expected_action
