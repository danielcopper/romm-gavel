"""The 409 resolution ladder and the identity check — SPEC.md normative core.

Stdlib only, pure functions: hashes in, decision out. Inputs are content hashes
as produced by RomM (``content_hash`` on a save) or recorded by the client at a
sync boundary; ``None`` and ``""`` both mean "unknown" and never prove anything.
"""

from __future__ import annotations

from typing import Literal


def local_matches_server(
    local_hash: str | None,
    server_content_hash: str | None,
    last_sync_hash: str | None,
    last_sync_server_hash: str | None,
) -> bool:
    """Whether the present local file is byte-identical to a server save.

    A disjunction of two routes, so a divergence between the client's local
    hashing and the server's own scheme never silently breaks identity:

    - **Provenance** (primary): the local file is unchanged since the recorded
      baseline (``local_hash == last_sync_hash``) AND that baseline was synced
      against this exact server content (``last_sync_server_hash ==
      server_content_hash``). Both compared server-side values are hashes the
      server itself produced, so this route holds even if the client's hashing
      drifts from the server's.
    - **Parity** (fallback): the local content hash equals the server content
      hash directly. The only route available to a file with no sync history on
      this device (fresh reinstall, copied storage, second device) — there is no
      stored server hash to anchor provenance. Correct only while the client's
      hashing reproduces the server's scheme, which is why it is the fallback.

    Every compared value must be truthy — a missing or empty hash on either
    side never reads as a match.
    """
    if (
        local_hash
        and local_hash == last_sync_hash
        and last_sync_server_hash
        and last_sync_server_hash == server_content_hash
    ):
        return True
    return bool(local_hash) and local_hash == server_content_hash


def resolve_upload_conflict(
    local_hash: str | None,
    last_sync_hash: str | None,
    server_content_hash: str | None = None,
    last_sync_server_hash: str | None = None,
) -> Literal["download", "conflict"]:
    """Decide the fallback after the server rejected an upload with 409.

    The server's 409 on an ``overwrite=false`` POST proves the slot's head moved
    past what this device last synced. Two provably-safe outcomes, else a user
    decision:

    - **L1** — local is unchanged since the recorded baseline
      (``local_hash == last_sync_hash``, both truthy): the client holds no
      un-synced work, nothing of its own to protect → ``"download"``.
    - **L2** — local is byte-identical to what the server now holds
      (:func:`local_matches_server`): adopting identical bytes loses nothing →
      ``"download"``. Inside the ladder the provenance route is subsumed by L1
      (it requires local unchanged since baseline), so here it is the parity
      fallback that decides — a local that diverged from the baseline yet
      reproduces the server head byte-for-byte.
    - **L3** — otherwise local carries changes AND the server independently
      moved (exactly what the 409 proves) → ``"conflict"`` for the user.

    Missing or empty information never yields ``"download"`` — the safe default
    under uncertainty is ``"conflict"``.
    """
    if local_hash and last_sync_hash and local_hash == last_sync_hash:
        return "download"
    if local_matches_server(local_hash, server_content_hash, last_sync_hash, last_sync_server_hash):
        return "download"
    return "conflict"
