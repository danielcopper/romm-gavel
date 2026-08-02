"""ctypes wrapper around a compiled gavel shared library.

The caller provides the path to a ``libgavel`` build (``.so``); the wrapper
declares the exported functions' C signatures and converts values at the
boundary:

- Python ``None``   → C ``NULL``        (no string at all)
- Python ``""``     → C empty string    (a real pointer to a ``'\\0'`` byte)
- Python ``str``    → UTF-8 bytes       (ctypes appends the terminating NUL)
- C ``int`` results → ``"download"``/``"conflict"`` and ``bool``

Preserving the ``None`` vs ``""`` distinction is load-bearing: the spec treats
both as "unknown", but they are different values on the wire and the vectors
deliberately probe both encodings.

:meth:`GavelCore.compute_sync_action` additionally repackages the reference's
dict inputs into the core's structs. Two conversions are the binding's own
responsibility rather than the core's:

- **Timestamps.** The core takes epoch seconds plus a "known" flag; turning a
  server save's ISO-8601 ``updated_at`` into that pair happens here, using the
  stdlib parser. What the *contract* says about timestamps — an unparseable one
  loses head selection and cannot prove local-newer — stays in the core, as its
  behavior when the flag is clear.
- **Optional numbers.** A missing dict key becomes a clear ``has_*`` flag, never
  a sentinel value: a size of 0 is exactly what the corrupt-local guard looks
  for, so it must not be confused with "no size recorded".
"""

from __future__ import annotations

import ctypes
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

_ACTIONS = {0: "skip", 1: "upload", 2: "download", 3: "conflict"}
_SKIP_REASONS = {0: "synced", 1: "nothing_to_sync"}


def _encode(value: str | None) -> bytes | None:
    """Map a hash value to its C representation (None → NULL, str → UTF-8)."""
    if value is None:
        return None
    return value.encode("utf-8")


def _parse_iso_to_epoch(value: str | None) -> float | None:
    """ISO-8601 → epoch seconds, or None on any parse failure.

    Mirrors ``gavel_reference.decision_table.parse_iso_to_epoch`` exactly — the
    decision-table vectors run through this function, so a divergence here is a
    conformance failure, not a detail.
    """
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return None


class _DeviceSync(ctypes.Structure):
    _fields_ = (("device_id", ctypes.c_char_p), ("is_current", ctypes.c_int))


class _ServerSave(ctypes.Structure):
    _fields_ = (
        ("id", ctypes.c_int64),
        ("updated_at_epoch", ctypes.c_double),
        ("has_updated_at", ctypes.c_int),
        ("content_hash", ctypes.c_char_p),
        ("device_syncs", ctypes.POINTER(_DeviceSync)),
        ("device_sync_count", ctypes.c_size_t),
    )


class _LocalFile(ctypes.Structure):
    _fields_ = (
        ("size", ctypes.c_int64),
        ("has_size", ctypes.c_int),
        ("mtime", ctypes.c_double),
        ("has_mtime", ctypes.c_int),
    )


class _Bookkeeping(ctypes.Structure):
    _fields_ = (
        ("last_sync_hash", ctypes.c_char_p),
        ("last_sync_server_hash", ctypes.c_char_p),
        ("last_sync_local_size", ctypes.c_int64),
        ("has_last_sync_local_size", ctypes.c_int),
    )


class _SyncAction(ctypes.Structure):
    _fields_ = (
        ("action", ctypes.c_int),
        ("reason", ctypes.c_int),
        ("adopt_baseline", ctypes.c_int),
        ("target_save_id", ctypes.c_int64),
        ("has_target_save_id", ctypes.c_int),
        ("server_save_id", ctypes.c_int64),
    )


def _optional_number(value: object) -> tuple[float, int]:
    """A dict value → the core's ``(number, has_number)`` pair.

    A number is present; anything else — an absent key, ``None``, a string —
    reads as absent. That is the reference's ``isinstance(x, int | float)``
    guard on ``mtime``, applied to every optional number: where the reference
    would raise on a non-numeric size, the core is simply told it has none, and
    the safe "cannot prove it" branch applies.
    """
    if isinstance(value, (int, float)):
        return float(value), 1
    return 0.0, 0


class GavelCore:
    """The gavel native core, loaded from a compiled shared library."""

    def __init__(self, library_path: str | Path) -> None:
        lib = ctypes.CDLL(str(library_path))
        # Declaring argtypes/restype is not optional politeness: without them
        # ctypes guesses (everything becomes a C int), which corrupts pointer
        # arguments on the way in and misreads results on the way out.
        lib.gavel_resolve_upload_conflict.argtypes = [ctypes.c_char_p] * 4
        lib.gavel_resolve_upload_conflict.restype = ctypes.c_int
        lib.gavel_local_matches_server.argtypes = [ctypes.c_char_p] * 4
        lib.gavel_local_matches_server.restype = ctypes.c_int
        lib.gavel_compute_sync_action.argtypes = [
            ctypes.POINTER(_LocalFile),
            ctypes.POINTER(_ServerSave),
            ctypes.c_size_t,
            ctypes.POINTER(_Bookkeeping),
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(_SyncAction),
        ]
        lib.gavel_compute_sync_action.restype = None
        self._lib = lib

    def resolve_upload_conflict(
        self,
        local_hash: str | None,
        last_sync_hash: str | None,
        server_content_hash: str | None = None,
        last_sync_server_hash: str | None = None,
    ) -> Literal["download", "conflict"]:
        """The 409 resolution ladder — same signature as the Python reference."""
        result = self._lib.gavel_resolve_upload_conflict(
            _encode(local_hash),
            _encode(last_sync_hash),
            _encode(server_content_hash),
            _encode(last_sync_server_hash),
        )
        return "download" if result == 0 else "conflict"

    def local_matches_server(
        self,
        local_hash: str | None,
        server_content_hash: str | None,
        last_sync_hash: str | None,
        last_sync_server_hash: str | None,
    ) -> bool:
        """The identity check — same signature as the Python reference."""
        return bool(
            self._lib.gavel_local_matches_server(
                _encode(local_hash),
                _encode(server_content_hash),
                _encode(last_sync_hash),
                _encode(last_sync_server_hash),
            )
        )

    def compute_sync_action(
        self,
        local_file: dict[str, Any] | None,
        server_saves_in_slot: list[dict[str, Any]],
        files_state: dict[str, Any],
        device_id: str,
        local_hash: str | None,
    ) -> dict[str, Any]:
        """The full sync decision — same signature as the Python reference.

        Takes and returns the reference's dict shapes (server saves still carry
        ISO-8601 ``updated_at``; the result speaks the vector dialect), so this
        is a drop-in swap for ``gavel_reference.compute_sync_action``.
        """
        # Every buffer the C structs point at must outlive the call. ctypes
        # keeps its own references, but an explicit list removes the question:
        # each encoded string and each array is reachable from here until
        # gavel_compute_sync_action has returned.
        keepalive: list[object] = []

        c_local_file = _build_local_file(local_file)
        c_saves, save_count = _build_saves(server_saves_in_slot, keepalive)
        c_bookkeeping = _build_bookkeeping(files_state, keepalive)
        encoded_device_id = _encode(device_id)
        encoded_local_hash = _encode(local_hash)

        result = _SyncAction()
        self._lib.gavel_compute_sync_action(
            c_local_file,
            c_saves,
            save_count,
            c_bookkeeping,
            encoded_device_id,
            encoded_local_hash,
            ctypes.byref(result),
        )
        return _decode_action(result)


def _build_local_file(local_file: dict[str, Any] | None) -> Any:
    """The local file struct pointer, or NULL when the file does not exist.

    Holds no strings, so ``ctypes.pointer`` keeping the struct alive is all the
    lifetime management it needs.
    """
    if local_file is None:
        return None
    size, has_size = _optional_number(local_file.get("size"))
    mtime, has_mtime = _optional_number(local_file.get("mtime"))
    return ctypes.pointer(_LocalFile(size=int(size), has_size=has_size, mtime=mtime, has_mtime=has_mtime))


def _build_bookkeeping(files_state: dict[str, Any], keepalive: list[object]) -> Any:
    """The bookkeeping record as a struct pointer.

    An empty ``files_state`` is still a record, not an absent one — the
    reference reads missing keys as ``None``, and a struct of unknowns says
    exactly that. (The core also accepts NULL here, which decides identically;
    raw-ABI callers with no record at all can use it.)
    """
    last_sync_hash = _encode(files_state.get("last_sync_hash"))
    last_sync_server_hash = _encode(files_state.get("last_sync_server_hash"))
    keepalive += [last_sync_hash, last_sync_server_hash]
    size, has_size = _optional_number(files_state.get("last_sync_local_size"))
    return ctypes.pointer(
        _Bookkeeping(
            last_sync_hash=last_sync_hash,
            last_sync_server_hash=last_sync_server_hash,
            last_sync_local_size=int(size),
            has_last_sync_local_size=has_size,
        )
    )


def _build_saves(server_saves_in_slot: list[dict[str, Any]], keepalive: list[object]) -> tuple[Any, int]:
    """The slot's server saves as one contiguous array, or NULL when empty.

    Each save's ``device_syncs`` gets its own array; both those arrays and every
    encoded string go into ``keepalive``, because assigning through an array
    element writes a raw pointer into the struct and the object behind it has to
    survive until the call returns.
    """
    if not server_saves_in_slot:
        return None, 0

    saves = (_ServerSave * len(server_saves_in_slot))()
    keepalive.append(saves)
    for index, save in enumerate(server_saves_in_slot):
        device_syncs = save.get("device_syncs") or []
        entries = (_DeviceSync * len(device_syncs))()
        keepalive.append(entries)
        for entry_index, entry in enumerate(device_syncs):
            device_id = _encode(entry.get("device_id"))
            keepalive.append(device_id)
            entries[entry_index].device_id = device_id
            entries[entry_index].is_current = 1 if entry.get("is_current") else 0

        content_hash = _encode(save.get("content_hash"))
        keepalive.append(content_hash)
        epoch = _parse_iso_to_epoch(save.get("updated_at"))
        saves[index].id = int(save["id"])
        saves[index].updated_at_epoch = 0.0 if epoch is None else epoch
        saves[index].has_updated_at = 0 if epoch is None else 1
        saves[index].content_hash = content_hash
        saves[index].device_syncs = ctypes.cast(entries, ctypes.POINTER(_DeviceSync))
        saves[index].device_sync_count = len(device_syncs)
    return saves, len(server_saves_in_slot)


def _decode_action(result: _SyncAction) -> dict[str, Any]:
    """The C result struct → the vector dialect's tagged dict."""
    action = _ACTIONS[result.action]
    if action == "skip":
        return {
            "action": "skip",
            "reason": _SKIP_REASONS[result.reason],
            "adopt_baseline": bool(result.adopt_baseline),
        }
    if action == "upload":
        return {
            "action": "upload",
            "target_save_id": result.target_save_id if result.has_target_save_id else None,
        }
    return {"action": action, "server_save_id": result.server_save_id}
