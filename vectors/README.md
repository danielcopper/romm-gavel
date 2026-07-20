# Conformance vectors

Language-neutral JSON test vectors. Each file carries one vector **family** (a top-level `family`, `spec`, and
`description`) and a `vectors` array of `{name, input, expected}` entries; curated vectors additionally carry a
`rationale`. Hash strings in inputs are placeholders — only presence and equality carry meaning; `null` means unknown,
and `""` (empty) is deliberately distinct from it, because implementations get the two wrong in different ways.

An implementation is conformant with a family when it produces `expected` for every vector in that family.
`scripts/validate_vectors.py` checks the file shape; `reference/tests/` runs every vector against the reference
implementation.

## Testing your implementation

1. **Copy the family's JSON files into your repo** (recommended over fetching at test time: no network in CI, and a
   vector update shows up as a reviewable diff on your side). Note the gavel commit you copied at, so updates are
   deliberate.
2. **Write a small adapter** from the vector input to your function. Your code probably doesn't take four loose hash
   parameters — Grout's `resolveUpload409` and Argosy's conflict resolution take richer objects. The adapter extracts
   the family's input fields, calls your implementation, and maps your outcome onto the family's expected values
   (`"download"` / `"conflict"` for the ladder).
3. **Run every vector and compare against `expected`.** One test case per vector, named after the vector's `name`, so a
   failure points at a specific, documented scenario (curated vectors carry the reasoning in `rationale`).

Two traps:

- **`null` and `""` are different on purpose.** `null` means the value is unknown/absent; `""` is an empty string that
  an implementation might wrongly treat as a real hash. Your adapter must preserve the distinction — a JSON loader or
  type mapping that collapses both onto one "falsy" value will still pass (the expected outcome is the same today), but
  it erases exactly the edge the two encodings exist to probe.
- **Hash strings are opaque placeholders.** Only presence and equality carry meaning — never length-check, parse, or
  recompute them.

Worked examples: `reference/tests/test_ladder_vectors.py` in this repo (the reference runner, ~40 lines), and
decky-romm-sync's `tests/domain/test_sync_action_gavel_vectors.py` with its `tests/domain/gavel_vectors/README.md` (the
vendoring pattern in a real client).

## `ladder/` — the 409 resolution ladder

Inputs are the four hash values of the ladder (`local_hash`, `last_sync_hash`, `server_content_hash`,
`last_sync_server_hash`); `expected` is `"download"` or `"conflict"`.

- `named-cases.json` — curated, named scenarios with rationales: the load-bearing cases by name.
- `equivalence-classes.json` — the exhaustive set: every canonical equality pattern over the four inputs (each slot
  absent / empty / one of up to four distinct values, canonicalized by first occurrence). 151 classes — complete over
  the abstraction, so any behavioral divergence from the ladder shows up here by construction.

## Planned families

- `decision-table/` — the full per-`(rom, filename, slot)` decision (informative in SPEC.md, but vectors let a client
  that adopts the reference model prove it): inputs as in the SPEC's Inputs table, expected as
  `{action, adopt_baseline?}`. This family is also what exercises the identity check's **provenance route**: inside the
  ladder that route is subsumed by L1, so the ladder vectors constrain only the parity route — a port's provenance leg
  is proven here, not above.
