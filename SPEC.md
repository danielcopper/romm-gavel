# gavel — save-sync decision spec

Status: **draft**, extracted from decky-romm-sync `domain/sync_action.py` (`compute_sync_action` +
`resolve_upload_conflict`).

## Scope

The layer RomM's Device Sync delegates to clients. **Detection (which side changed) is out of scope** — negotiate owns
it. Normative here: what a client records at each sync boundary (its own baseline hash plus the server-stamped
`content_hash`), the identity check, the 409/conflict resolution ladder, overwrite discipline, and the safety
invariants. Resolution of a surfaced conflict (keep-local vs use-server) is a user decision; the spec defines _when_ it
must be surfaced, never picks the winner.

The full per-`(rom, filename, slot)` decision table below is **informative**: it documents the reference client's model,
which keeps detection client-side by choice. Clients that consume negotiate's verdicts directly still need the normative
parts — the bookkeeping and the ladder are exactly where shipped clients diverge today.

## Bookkeeping (normative)

At each **successful sync boundary** — an upload the server acknowledged, a completed download, or an explicit baseline
adoption — the client records, per synced file:

| Field                   | Value                                                                                         |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| `last_sync_hash`        | the client's own content hash of the local file as it existed at that boundary (the baseline) |
| `last_sync_server_hash` | the server's `content_hash` for the same synced version, stored verbatim                      |
| `last_sync_local_size`  | the local file's size at that boundary (backs invariant I3)                                   |

Rules:

- Recorded only at successful boundaries, never speculatively. A failed upload or an interrupted download leaves the
  previous record untouched.
- `last_sync_server_hash` is stored **verbatim** — remember what the server said, don't recompute it. It is the primary
  identity anchor and survives any drift between the client's hashing and the server's scheme.
- A value the client could not obtain is recorded as absent, never as an empty string. Absent means "unknown", and
  unknown never proves anything (see the identity check).
- A server-side per-device baseline, if RomM ships one, is an alternative **source** for these values — not a rule
  change.

## The identity check (normative)

_"Is my local file byte-identical to that server save?"_ — answered by a disjunction of two routes, so a divergence
between the client's local hashing and the server's own scheme never silently breaks identity:

- **Provenance** (primary): the local file is unchanged since the recorded baseline (`local_hash == last_sync_hash`) AND
  that baseline was synced against this exact server content (`last_sync_server_hash == content_hash`). Both server-side
  operands are hashes the server itself produced, so this route holds even if the client's hashing drifts from the
  server's.
- **Parity** (fallback): the local content hash equals the server's `content_hash` directly. The only route available to
  a file with no sync history on this device (fresh reinstall, copied storage, second device) — there is no stored
  server hash to anchor provenance. Correct only while the client's hashing reproduces the server's scheme, which is why
  it is the fallback, not the primary.

Every compared value must be present and non-empty — a missing or empty hash on either side never reads as a match.

## The 409 resolution ladder (normative)

Automatic uploads POST with `overwrite=false`. The server's 409 on such a POST proves the slot's head moved past what
this device last synced — the decision that led to the upload was made against a snapshot that went stale. The client
MUST then re-decide from hashes alone, in order:

1. **L1 — unchanged since baseline**: `local_hash == last_sync_hash` (both present and non-empty) → **download**. The
   client holds no un-synced work; there is nothing of its own to protect.
2. **L2 — byte-identical to the head**: the identity check passes against the server's current head → **download**.
   Adopting identical bytes loses nothing. (Inside the ladder the provenance route is subsumed by L1, so here it is the
   parity fallback that decides — a local that diverged from the baseline yet reproduces the server head byte-for-byte.)
3. **L3 — otherwise**: local carries changes AND the server independently moved (exactly what the 409 proves) →
   **conflict**, surfaced to the user.

Missing or empty information never yields **download** — the safe default under uncertainty is **conflict**.

## Overwrite discipline (normative)

- Every automatic upload POSTs a new save with `overwrite=false`. The server's 409 is the write-time currency backstop;
  the client never pre-empts it by forcing.
- `overwrite=true` is sent only to execute an explicit user **keep-local** decision on a surfaced conflict. No automatic
  path ever forces.
- After a 409 the client runs the ladder. It does not retry the POST unchanged and does not escalate to `overwrite=true`
  on its own.

## Inputs

| Input                  | Shape                                                                                                    | Source                                 |
| ---------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `local_file`           | `{filename, size, mtime}` or absent                                                                      | client filesystem                      |
| `server_saves_in_slot` | list of RomM save objects (`id`, `updated_at`, `content_hash`, `device_syncs[].{device_id, is_current}`) | RomM API                               |
| `device_id`            | string                                                                                                   | RomM device registration               |
| `local_hash`           | content hash of the local file, or unknown                                                               | client (RomM-parity scheme, zip-aware) |
| bookkeeping record     | `last_sync_hash`, `last_sync_server_hash`, `last_sync_local_size`, or absent                             | client-held state (see Bookkeeping)    |

## Decision table (informative)

The reference client's full model — one decision per `(rom, filename, slot)`:

1. **No server saves in slot** → upload if a local file exists, else nothing to sync.
2. **Pick the newest server save** by `updated_at` (deterministic; unparseable timestamps lose).
3. **Branch on this device's `device_syncs` entry** on that save:

**`is_current=true`** — the server still tracks this device's last version:

| Local file | Baseline                             | Action                                       |
| ---------- | ------------------------------------ | -------------------------------------------- |
| absent     | —                                    | download (recover the tracked content)       |
| present    | none                                 | skip + adopt baseline                        |
| present    | unchanged                            | skip (synced)                                |
| present    | diverged, local implausibly shrunken | conflict (corrupt-local guard, invariant I3) |
| present    | diverged                             | upload (`overwrite=false`; a 409 → ladder)   |

**`is_current=false`** — the server head moved past this device:

| Local file | Baseline  | Identity vs head | Action                                         |
| ---------- | --------- | ---------------- | ---------------------------------------------- |
| absent     | —         | —                | download                                       |
| present    | none      | match            | download (harmless, re-anchors baseline)       |
| present    | none      | no match         | conflict (unknown provenance)                  |
| present    | unchanged | —                | download                                       |
| present    | diverged  | match            | download (both moves landed on the same bytes) |
| present    | diverged  | no match         | conflict (true two-sided divergence)           |

**no entry** — this device never touched the chosen save:

| Local file | Baseline                  | Identity vs head | Action                                               |
| ---------- | ------------------------- | ---------------- | ---------------------------------------------------- |
| absent     | —                         | —                | download                                             |
| present    | —                         | match            | skip + adopt baseline (don't POST a duplicate)       |
| present    | held, diverged            | no match         | conflict (mirrors `is_current=false`)                |
| present    | none, hash known          | no match         | conflict (unknown provenance, both mtime directions) |
| present    | unchanged or hash unknown | —                | mtime ≥ server `updated_at` → upload, else download  |

Notes:

- The local hash is computed with the server-parity scheme (zip-aware), so parity comparisons can match for archived
  saves too.
- Known gap in the reference client: a server save without `content_hash` (older/migrated data) skips the dedup check on
  the mtime path and can POST a byte-identical duplicate. Harmless (the server dedups content), but documented.

## Invariants

- **I1** — No destructive action without a recovery source.
- **I2** — Never silently overwrite an unbacked local edit.
- **I3** — A corrupt or implausibly shrunken local file never auto-uploads.
- **I4** — Byte-identity (hash equality with the server save) is always safe to adopt.
- **I5** — Automatic uploads never force-overwrite; the server's 409 is the write-time backstop, and the fallback
  re-decides from hashes only (unchanged local → download; anything else → conflict). Force-overwrite happens only on an
  explicit user keep-local.
- **I6** — Under missing or unparseable information, the safe default is the server copy for reads and `conflict` for
  writes — never a silent local overwrite in either direction.

## Conformance

An implementation is conformant when it produces the expected action for every vector in `vectors/`. Vectors are the
normative artifact; prose explains, vectors decide.

Current coverage: the 409 resolution ladder (`vectors/ladder/` — a curated named set plus the exhaustive
equivalence-class set over the four hash inputs) and the decision table (`vectors/decision-table/` — curated named cases
across every branch and row above, including both identity routes and the timestamp fall-through).
