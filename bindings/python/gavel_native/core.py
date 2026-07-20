"""ctypes wrapper around a compiled gavel shared library.

The caller provides the path to a ``libgavel`` build (``.so``); the wrapper
declares the two exported functions' C signatures and converts values at the
boundary:

- Python ``None``   → C ``NULL``        (no string at all)
- Python ``""``     → C empty string    (a real pointer to a ``'\\0'`` byte)
- Python ``str``    → UTF-8 bytes       (ctypes appends the terminating NUL)
- C ``int`` results → ``"download"``/``"conflict"`` and ``bool``

Preserving the ``None`` vs ``""`` distinction is load-bearing: the spec treats
both as "unknown", but they are different values on the wire and the vectors
deliberately probe both encodings.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Literal


def _encode(value: str | None) -> bytes | None:
    """Map a hash value to its C representation (None → NULL, str → UTF-8)."""
    if value is None:
        return None
    return value.encode("utf-8")


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
