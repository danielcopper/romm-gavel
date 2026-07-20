"""The reference model's full sync decision — SPEC.md's informative decision table.

One decision per (rom, filename, slot): given the local file, the slot's server
saves, the bookkeeping record, and this device's id, produce the action. Clients
that consume negotiate's verdicts directly don't need this module — it exists
for clients that, like the reference client, compute detection themselves.

The return value speaks the vector dialect (the ``expected`` shape of the
``decision-table`` family) so the conformance runner is a single comparison. A
real client returns whatever fits its internals; only the decision must match.

Stdlib only, pure functions: state in, decision out.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from gavel_reference.ladder import local_matches_server

SHRINK_RATIO = 0.5


def parse_iso_to_epoch(value: str | None) -> float | None:
    """ISO-8601 → epoch seconds, or None on any parse failure."""
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return None


def is_implausibly_shrunken(new_size: int | None, baseline_size: int | None) -> bool:
    """A 0-byte file is never a plausible edit; below half the recorded size is a truncated write."""
    if new_size is None:
        return False
    if new_size == 0:
        return True
    if baseline_size is None or baseline_size <= 0:
        return False
    return new_size < baseline_size * SHRINK_RATIO


def _local_mtime_ge_head(local_file: dict[str, Any], head: dict[str, Any]) -> bool:
    """Local-newer-or-equal on the timestamp fall-through; any parse failure means the server wins."""
    local_mtime = local_file.get("mtime")
    if not isinstance(local_mtime, int | float):
        return False
    head_epoch = parse_iso_to_epoch(head.get("updated_at", ""))
    if head_epoch is None:
        return False
    return local_mtime >= head_epoch


def _skip(reason: str, adopt_baseline: bool = False) -> dict[str, Any]:
    return {"action": "skip", "reason": reason, "adopt_baseline": adopt_baseline}


def _upload(target_save_id: int | None) -> dict[str, Any]:
    return {"action": "upload", "target_save_id": target_save_id}


def _download(head: dict[str, Any]) -> dict[str, Any]:
    return {"action": "download", "server_save_id": head["id"]}


def _conflict(head: dict[str, Any]) -> dict[str, Any]:
    return {"action": "conflict", "server_save_id": head["id"]}


def _decide_when_is_current(
    head: dict[str, Any],
    local_file: dict[str, Any] | None,
    local_hash: str | None,
    last_sync_hash: str | None,
    last_sync_local_size: int | None,
) -> dict[str, Any]:
    """The server still tracks this device's last version on the head."""
    if local_file is None:
        return _download(head)
    if not last_sync_hash:
        return _skip("synced", adopt_baseline=True)
    if local_hash and local_hash != last_sync_hash:
        if is_implausibly_shrunken(local_file.get("size"), last_sync_local_size):
            return _conflict(head)
        return _upload(head.get("id"))
    return _skip("synced")


def _decide_when_not_current(
    head: dict[str, Any],
    local_file: dict[str, Any] | None,
    local_hash: str | None,
    last_sync_hash: str | None,
    last_sync_server_hash: str | None,
) -> dict[str, Any]:
    """The server head moved past this device."""
    if local_file is None:
        return _download(head)
    if not last_sync_hash:
        if local_matches_server(local_hash, head.get("content_hash"), last_sync_hash, last_sync_server_hash):
            return _download(head)
        return _conflict(head)
    if local_hash and local_hash != last_sync_hash:
        if local_matches_server(local_hash, head.get("content_hash"), last_sync_hash, last_sync_server_hash):
            return _download(head)
        return _conflict(head)
    return _download(head)


def _decide_when_no_entry(
    head: dict[str, Any],
    local_file: dict[str, Any] | None,
    local_hash: str | None,
    last_sync_hash: str | None,
    last_sync_server_hash: str | None,
) -> dict[str, Any]:
    """This device never touched the chosen head."""
    if local_file is None:
        return _download(head)
    if local_matches_server(local_hash, head.get("content_hash"), last_sync_hash, last_sync_server_hash):
        return _skip("synced", adopt_baseline=True)
    if last_sync_hash and local_hash and local_hash != last_sync_hash:
        return _conflict(head)
    if not last_sync_hash and local_hash:
        return _conflict(head)
    if _local_mtime_ge_head(local_file, head):
        return _upload(None)
    return _download(head)


def compute_sync_action(
    local_file: dict[str, Any] | None,
    server_saves_in_slot: list[dict[str, Any]],
    files_state: dict[str, Any],
    device_id: str,
    local_hash: str | None,
) -> dict[str, Any]:
    """Compute the sync decision for a single (rom, filename, slot) triple."""
    if not server_saves_in_slot:
        if local_file:
            return _upload(None)
        return _skip("nothing_to_sync")

    head = max(
        server_saves_in_slot,
        key=lambda s: parse_iso_to_epoch(s.get("updated_at")) or 0.0,
    )

    device_syncs = head.get("device_syncs") or []
    our_entry = next((ds for ds in device_syncs if ds.get("device_id") == device_id), None)
    last_sync_hash = files_state.get("last_sync_hash")
    last_sync_server_hash = files_state.get("last_sync_server_hash")
    last_sync_local_size = files_state.get("last_sync_local_size")

    if our_entry and our_entry.get("is_current"):
        return _decide_when_is_current(head, local_file, local_hash, last_sync_hash, last_sync_local_size)
    if our_entry is not None:
        return _decide_when_not_current(head, local_file, local_hash, last_sync_hash, last_sync_server_hash)
    return _decide_when_no_entry(head, local_file, local_hash, last_sync_hash, last_sync_server_hash)
