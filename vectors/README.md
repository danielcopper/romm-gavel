# Conformance vectors

Language-neutral JSON test vectors. Each file carries one vector **family** (a top-level `family`, `spec`, and
`description`) and a `vectors` array of `{name, input, expected}` entries; curated vectors additionally carry a
`rationale`. Hash strings in inputs are placeholders — only presence and equality carry meaning; `null` means unknown,
and `""` (empty) is deliberately distinct from it, because implementations get the two wrong in different ways.

An implementation is conformant with a family when it produces `expected` for every vector in that family.
`scripts/validate_vectors.py` checks the file shape; `reference/tests/` runs every vector against the reference
implementation.

## Testing your implementation

1. **Copy the JSON files of the family you want to conform to into your repo** — the two files in `vectors/ladder/`, the
   one in `vectors/decision-table/`, or both. Copying is recommended over fetching at test time: no network in CI, and a
   vector update shows up as a reviewable diff on your side. Note the gavel release tag you copied at, so updates are
   deliberate.
2. **Write a small adapter** from the vector input to your function. Your code probably doesn't take four loose hash
   parameters but the objects it already passes around internally — the adapter is just the repackaging: extract the
   family's input fields, call your implementation, and map your outcome onto the family's expected values (`"download"`
   / `"conflict"` for the ladder). In a TypeScript client it looks like this:

   ```ts
   import cases from "./gavel-vectors/named-cases.json";

   for (const vector of cases.vectors) {
     const got = resolveUpload409({
       localHash: vector.input.local_hash, // null must stay null, "" must stay ""
       baselineHash: vector.input.last_sync_hash,
       serverHash: vector.input.server_content_hash,
       rememberedServerHash: vector.input.last_sync_server_hash,
     });
     assert(got === vector.expected, `${vector.name}: ${vector.rationale ?? ""}`);
   }
   ```

3. **Run every vector and compare against `expected`.** One test case per vector, named after the vector's `name`, so a
   failure points at a specific, documented scenario (curated vectors carry the reasoning in `rationale`).

Two traps:

- **`null` and `""` are different on purpose.** `null` means the value is unknown/absent; `""` is an empty string that
  an implementation might wrongly treat as a real hash. Your adapter must preserve the distinction — a JSON loader or
  type mapping that collapses both onto one "falsy" value will still pass (the expected outcome is the same today), but
  it erases exactly the edge the two encodings exist to probe.
- **Hash strings are opaque placeholders.** Only presence and equality carry meaning — never length-check, parse, or
  recompute them.

Worked examples: `reference/tests/test_ladder_vectors.py` in this repo (the reference runner, ~40 lines) and
`core/tests/test_core_decision_table_vectors.py` (the same for the richer family, including how the nested input objects
map onto the C ABI); decky-romm-sync's `tests/domain/test_sync_action_gavel_vectors.py` with its
`tests/domain/gavel_vectors/README.md` (the vendoring pattern in a real client).

**If you'd rather not implement it at all**, `core/` is the same contract compiled: a freestanding C ABI with a Python
binding over it, running these vectors in CI. Vendor the released `.so` against its published checksum and the
conformance question stops being yours.

## `ladder/` — the 409 resolution ladder

Inputs are the four hash values of the ladder (`local_hash`, `last_sync_hash`, `server_content_hash`,
`last_sync_server_hash`); `expected` is `"download"` or `"conflict"`.

- `named-cases.json` — curated, named scenarios with rationales: the load-bearing cases by name.
- `equivalence-classes.json` — the exhaustive set: every canonical equality pattern over the four inputs (each slot
  absent / empty / one of up to four distinct values, canonicalized by first occurrence). 151 classes — complete over
  the abstraction, so any behavioral divergence from the ladder shows up here by construction.

## `decision-table/` — the full sync decision

The per-`(rom, filename, slot)` decision of the reference model (informative in SPEC.md — clients that consume
negotiate's verdicts directly don't need this family; clients that compute detection themselves can prove their model
with it). Inputs mirror the SPEC's Inputs table: `local_file` (object or `null`), `server_saves_in_slot` (list of RomM
save objects), `files_state` (the bookkeeping record, keys may be absent), `device_id`, `local_hash`. `expected` is a
tagged object: `{action: "skip", reason, adopt_baseline}`, `{action: "upload", target_save_id}`, or
`{action: "download" | "conflict", server_save_id}`.

- `named-cases.json` — curated cases across every branch and row of the decision table: head selection (newest
  `updated_at`, unparseable loses), all three `device_syncs` branches, the corrupt-local guard, and the timestamp
  fall-through. Timestamps in inputs always carry an explicit UTC offset so parsing is environment-independent.

This family is also what exercises the identity check's **provenance route**: inside the ladder that route is subsumed
by L1, so the ladder vectors constrain only the parity route — a port's provenance leg is proven here
(`never-synced-provenance-dedup`), not above.
