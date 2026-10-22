# gavel — save-sync decision spec

Status: **stable**. Extracted from decky-romm-sync `domain/sync_action.py` (`compute_sync_action` +
`resolve_upload_conflict`), which now runs the compiled core instead. What a release promises, and what it does not, is
[below](#what-a-release-promises).

## Scope

The layer RomM's Device Sync delegates to clients. **Detection (which side changed) is out of scope** — negotiate owns
it. Normative here: what a client records at each sync boundary (its own baseline hash plus the server-stamped
`content_hash`), the identity check, the 409/conflict resolution ladder, overwrite discipline, and the safety
invariants. Resolution of a surfaced conflict (keep-local vs use-server) is a user decision; the spec defines _when_ it
must be surfaced, never picks the winner.

The full per-`(rom, filename, slot)` decision table below is **informative**: it documents the reference client's model,
which keeps detection client-side by choice. Clients that consume negotiate's verdicts directly still need the normative
parts — the bookkeeping and the ladder are exactly where shipped clients diverge today. Informative means "not required
of every client", not "not pinned": a client that does compute detection itself is held to
[`vectors/decision-table/`](vectors/decision-table/) exactly as tightly as to the ladder. See
[Conformance](#conformance).

**Which assets this covers.** The contract's inputs are a server-stamped `content_hash`, a per-device sync record and a
slot. RomM gives saves all three and save states none of them, and its sync endpoints do not cover states at all — so
this contract covers saves. Nothing in the rules is save-specific; they compare content hashes and never look at what a
file means. But an asset the server does not stamp cannot be decided by them: both routes of the identity check lose
their server-side operand, no `device_syncs` entry exists to branch on, and every decision falls through to the
timestamp comparison — the weakest path in the table, as the only path. Extending the contract to another asset type is
therefore a server question before it is a spec one.

## Bookkeeping (normative)

At each **successful sync boundary** — an upload the server acknowledged, a completed download, or an explicit baseline
adoption — the client records, per synced file:

| Field                    | Value                                                                                         |
| ------------------------ | --------------------------------------------------------------------------------------------- |
| `last_sync_hash`         | the client's own content hash of the local file as it existed at that boundary (the baseline) |
| `last_sync_server_hash`  | the server's `content_hash` for the same synced version, stored verbatim                      |
| `last_sync_local_size`   | the local file's size at that boundary (backs invariant I3)                                   |
| `last_sync_content_size` | the local file's content size at that boundary (see Inputs; backs invariant I3)               |

Rules:

- Recorded only at successful boundaries, never speculatively. A failed upload or an interrupted download leaves the
  previous record untouched.
- `last_sync_server_hash` is stored **verbatim** — remember what the server said, don't recompute it. It is the primary
  identity anchor and survives any drift between the client's hashing and the server's scheme.
- A value the client could not obtain is recorded as absent, never as an empty string. Absent means "unknown", and
  unknown never proves anything (see the identity check).
- Adopting a head this device is not current on is a sync boundary for the server as well: the client MUST acknowledge
  it to the server as synced. On RomM that is `POST /api/saves/{id}/downloaded` with the `device_id`, which records the
  device's sync row for that save without a transfer. Without it the server keeps the device not current on the head,
  and the next local change reads as a local edit under a head that moved past it — a conflict no other device caused.
  The decision table marks this case (see its result fields).
- Such an adoption is a successful boundary only once the server has confirmed the acknowledgement: the client records
  the new baseline after the acknowledgement succeeded, never before. A failed acknowledgement leaves the previous
  record untouched, and with nothing else changed the next run decides the same way again — adopt and acknowledge, no
  transfer.
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
| `local_file`           | `{filename, size, content_size, mtime}` or absent                                                        | client filesystem                      |
| `server_saves_in_slot` | list of RomM save objects (`id`, `updated_at`, `content_hash`, `device_syncs[].{device_id, is_current}`) | RomM API                               |
| `device_id`            | string                                                                                                   | RomM device registration               |
| `local_hash`           | content hash of the local file, or unknown                                                               | client (RomM-parity scheme, zip-aware) |
| bookkeeping record     | `last_sync_hash`, `last_sync_server_hash`, `last_sync_local_size`, `last_sync_content_size`, or absent   | client-held state (see Bookkeeping)    |

**`local_file` presence is the existence of the file, not what is known about it** (normative). Absent means there is no
local file at all; anything else is a present file, including one whose `size` or `mtime` the client could not read.
Presence is a two-valued question and implementations must keep it that way — a representation that lets "present"
degrade into "absent" once the fields are missing will answer the same state two different ways in different branches.
Getting it wrong is not symmetric: reading a present file as absent can leave the only copy unbacked in silence, while
reading an absent one as present fails loudly in the client's own file I/O.

Individual field values stay optional and unknown-tolerant as the decision table describes — an unknown `size` or
`content_size` merely means the corrupt-local guard decides on what is known (see the note under the `is_current=true`
table), not that the file is gone.

**The content size** (normative) is a file's size less the trailing run of the byte the file ends with, when that byte
is `0xFF` or `0x00`, the two fill bytes. A file ending in any other byte has a content size equal to its size; a file of
fill only, like an empty one, has content size 0. It is defined here so every client computes it alike: the guard
compares the local file's `content_size` with the recorded `last_sync_content_size`, and the core and the vectors read
both by this definition. The client computes it from the file's bytes.

## Decision table (informative)

The reference client's full model — one decision per `(rom, filename, slot)`:

1. **No server saves in slot** → upload if a local file exists, else nothing to sync.
2. **Pick the newest server save** by `updated_at` (deterministic; unparseable timestamps lose).
3. **Branch on this device's `device_syncs` entry** on that save:

**`is_current=true`** — the server still tracks this device's last version:

| Local file | Baseline                             | Identity vs head | Action                                       |
| ---------- | ------------------------------------ | ---------------- | -------------------------------------------- |
| absent     | —                                    | —                | download (recover the tracked content)       |
| present    | none                                 | match            | skip + adopt baseline                        |
| present    | none                                 | no match         | conflict (unknown provenance)                |
| present    | unchanged                            | —                | skip (synced)                                |
| present    | diverged, local implausibly shrunken | —                | conflict (corrupt-local guard, invariant I3) |
| present    | diverged                             | —                | upload (`overwrite=false`; a 409 → ladder)   |

The corrupt-local guard reads _implausibly shrunken_ as: a `size` of 0; else, where the local file and the bookkeeping
record both state a content size, a `content_size` below half of `last_sync_content_size`; else a `size` below half of
`last_sync_local_size`. A non-empty file of fill only is not refused for that alone: where both content sizes are
stated, it trips the guard whenever the recorded content was larger than 0.

**`is_current=false`** — the server does not hold this device as current on the head: the head moved past it, or (on
RomM with a `device_id`) it never synced this save:

| Local file | Baseline  | Identity vs head | Action                                                             |
| ---------- | --------- | ---------------- | ------------------------------------------------------------------ |
| absent     | —         | —                | download                                                           |
| present    | —         | match            | skip + adopt baseline + acknowledge (identical bytes never travel) |
| present    | none      | no match         | conflict (unknown provenance)                                      |
| present    | unchanged | no match         | download                                                           |
| present    | diverged  | no match         | conflict (true two-sided divergence)                               |

**no entry** — the listing carries no entry for this device (on RomM: a listing sent without a `device_id`):

| Local file | Baseline                  | Identity vs head | Action                                               |
| ---------- | ------------------------- | ---------------- | ---------------------------------------------------- |
| absent     | —                         | —                | download                                             |
| present    | —                         | match            | skip + adopt baseline (don't POST a duplicate)       |
| present    | held, diverged            | no match         | conflict (mirrors `is_current=false`)                |
| present    | none, hash known          | no match         | conflict (unknown provenance, both mtime directions) |
| present    | unchanged or hash unknown | —                | mtime ≥ server `updated_at` → upload, else download  |

Why a `device_id` keeps a RomM listing out of this branch: with one, every save in a RomM 5.x listing carries an entry
for the caller; where RomM holds no sync row for the device, that entry is synthesized: `is_current: false`,
`last_synced_at` set to the save's `updated_at`, and not stored (`backend/endpoints/saves.py`, `_build_save_schema`).

A skip that adopts a baseline names the head it adopted (`server_save_id`, the chosen head) and says whether the client
must acknowledge that head to the server (`acknowledge`, see Bookkeeping). `acknowledge` is set exactly on the adoption
in the `is_current=false` branch: in the `is_current=true` branch the device is already current, and with no entry the
listing reports no currency for this device, so there is nothing it says to correct (on RomM the listing was sent
without a `device_id`, the id the acknowledgement needs). A skip that adopts nothing names no head.

Notes:

- The local hash is computed with the server-parity scheme (zip-aware), so parity comparisons can match for archived
  saves too.
- Known gap in the reference client: a server save without `content_hash` (older/migrated data) skips the dedup check on
  the mtime path and can POST a byte-identical duplicate. Harmless (the server dedups content), but documented.

## Invariants

- **I1** — No destructive action without a recovery source.
- **I2** — Never silently overwrite an unbacked local edit.
- **I3** — A corrupt or implausibly shrunken local file never auto-uploads. A shrink that drops only trailing fill is
  not a shrink.
- **I4** — Byte-identity (hash equality with the server save) is always safe to adopt.
- **I5** — Automatic uploads never force-overwrite; the server's 409 is the write-time backstop, and the fallback
  re-decides from hashes only (unchanged local → download; anything else → conflict). Force-overwrite happens only on an
  explicit user keep-local.
- **I6** — Under missing or unparseable information, the safe default is the server copy for reads and `conflict` for
  writes — never a silent local overwrite in either direction.

## Conformance

Conformance is **per family**. An implementation is conformant with a vector family when it produces the expected action
for every vector in that family, and claims the families it implements rather than all of them. Vectors are the
normative artifact; prose explains, vectors decide.

Which families apply depends on where the client sits:

- **`vectors/ladder/`** — the 409 resolution ladder. Applies to every client that uploads, because every client
  eventually meets a 409. A curated named set plus the exhaustive equivalence-class set over the four hash inputs.
- **`vectors/decision-table/`** — the full per-`(rom, filename, slot)` decision. Applies to clients that compute
  detection themselves; a client consuming negotiate's verdicts directly has no use for it. Curated named cases across
  every branch and row of the table above, including both identity routes and the timestamp fall-through.

"Informative" above means exactly this — not required of every client. It does not mean optional to get right: where a
family applies, its vectors decide, and there is no weaker standard for one family than another.

Releases version the repository as a whole, so a changed `expected` anywhere is a major release (see
[`CONTRIBUTING.md`](CONTRIBUTING.md)). The obligation it creates is narrower than the version number suggests: only
implementers of the family whose vector changed have to act. A client conformant with the ladder alone can take a major
bump that asks nothing of it — which is why a client should record **which families** it conforms to, not just which
gavel release it pinned.

## What a release promises

Two surfaces are covered, because both are things a client depends on and neither can change without breaking it. Either
one changing incompatibly is a **major** release.

**The contract.** Every vector's `expected` value, and the normative sections above: bookkeeping, the identity check,
the ladder, overwrite discipline, and the invariants. Adding vectors or a family grows the contract without breaking it
— that is a minor.

**The C ABI** in [`core/gavel.h`](core/gavel.h), for clients that vendor the compiled core rather than implement the
contract themselves:

- the layout of `gavel_device_sync`, `gavel_server_save`, `gavel_local_file`, `gavel_bookkeeping` and
  `gavel_sync_action` — field order and types,
- the signatures of `gavel_local_matches_server`, `gavel_resolve_upload_conflict` and `gavel_compute_sync_action`,
- the enumerator values of `gavel_action` and `gavel_skip_reason`,
- the input conventions the header states: arrays as pointer plus count, optional numbers as a value plus an explicit
  `has_*` flag, timestamps as epoch seconds plus a known-flag, and presence of the local file carried by the pointer.

Adding an exported function is a minor. Adding a field to an existing struct is not — it moves the fields after it, so
it is a major even though nothing was removed.

**Not promised**, and free to change in any release: the pure-Python reference under `reference/` (it exists so the
vectors have a first consumer, not as an API), the internals of `bindings/python/`, the test harnesses, and the build
tooling.
