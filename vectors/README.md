# Conformance vectors

Language-neutral JSON test vectors. Each file carries one vector **family** (a top-level `family`, `spec`, and
`description`) and a `vectors` array of `{name, input, expected}` entries; curated vectors additionally carry a
`rationale`. Hash strings in inputs are placeholders — only presence and equality carry meaning; `null` means unknown,
and `""` (empty) is deliberately distinct from it, because implementations get the two wrong in different ways.

An implementation is conformant with a family when it produces `expected` for every vector in that family.
`scripts/validate_vectors.py` checks the file shape; `reference/tests/` runs every vector against the reference
implementation.

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
