# gavel — save-sync decision spec

Status: **draft, extraction in progress** from decky-romm-sync `domain/sync_action.py` (`compute_sync_action` + `resolve_upload_conflict`).

## Scope

One decision per `(rom, filename, slot)` triple: given the local file, the server saves in the slot, and what this device knows about its last sync, return exactly one action — `skip`, `upload`, `download`, or `conflict`. Resolution of a `conflict` (keep-local vs use-server) is a user decision and out of scope for the automatic path; the spec only defines *when* it must be surfaced.

## Inputs

| Input | Shape | Source |
| --- | --- | --- |
| `local_file` | `{filename, size, mtime}` or absent | client filesystem |
| `server_saves_in_slot` | list of RomM save objects (`id`, `updated_at`, `content_hash`, `device_syncs[].{device_id, is_current}`) | RomM API |
| `device_id` | string | RomM device registration |
| `local_hash` | content hash of the local file, or unknown | client (RomM-parity scheme, zip-aware) |
| `baseline` | last-synced content hash + size, or absent | client-held state (a future server-side per-device baseline is an alternative source, not a rule change) |

## Decision table

To be extracted. Branch structure of the reference implementation:

1. No server saves in slot → upload if a local file exists, else nothing to sync.
2. Pick the newest server save by `updated_at` (deterministic; unparseable timestamps lose).
3. Branch on this device's `device_syncs` entry on that save: `is_current=true` / `is_current=false` / no entry.

## Invariants

- **I1** — No destructive action without a recovery source.
- **I2** — Never silently overwrite an unbacked local edit.
- **I3** — A corrupt or implausibly shrunken local file never auto-uploads.
- **I4** — Byte-identity (hash equality with the server save) is always safe to adopt.
- **I5** — Automatic uploads never force-overwrite; the server's 409 is the write-time backstop, and the fallback re-decides from hashes only (unchanged local → download; anything else → conflict). Force-overwrite happens only on an explicit user keep-local.
- **I6** — Under missing or unparseable information, the safe default is the server copy for reads and `conflict` for writes — never a silent local overwrite in either direction.

## Conformance

An implementation is conformant when it produces the expected action for every vector in `vectors/`. Vectors are the normative artifact; prose explains, vectors decide.
