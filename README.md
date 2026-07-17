# romm-gavel

Save-sync conflict decisions for the RomM ecosystem — written down as a spec, not re-guessed per client.

## Why

Every RomM client that syncs saves has to answer the same question: local save vs server save — who wins, and when must a human decide? Today at least three clients (decky-romm-sync, Grout, Argosy) each re-implement basically the same hash-anchored resolver in three different languages. RomM's Device Sync protocol deliberately leaves this to the client: the server detects, it does not resolve — there is no resolve endpoint and no keep-both / server-wins directive anywhere in the API.

gavel is the decision half of the story. [sigil](https://github.com/rommforge/argosy-sigil) answers *"which game is this and what will its save be called"* — gavel answers *"which copy of the save wins"*.

The rules are not save-specific either: anything RomM syncs as a local-file-vs-server-version pair gets the same decision table — saves today, save states as the natural next consumer.

## What lives here

1. **`SPEC.md`** — the decision rules, written down: the inputs, every branch of the decision table, and the safety invariants (no destructive action without a recovery source; never silently overwrite an unbacked local edit; a corrupt or implausibly shrunken local never auto-uploads; overwrite only on an explicit keep-local; the server's 409 as the write-time backstop).
2. **`vectors/`** — the decision table as language-neutral JSON conformance vectors (`input → expected action`). Any implementation in any language can run them and prove it decides the same way.
3. **`reference/`** — a pure-Python reference implementation, extracted from decky-romm-sync's production kernel.
4. **Planned: a native core** with a C ABI plus per-language bindings (sigil-style), for clients that want a drop-in instead of maintaining their own implementation. Spec and vectors come first — they define what the core must do and prove it does it.

## What does not live here

- **File I/O, hashing, transport, UI.** gavel decides; reading files, computing hashes and talking to the server stay in the client.
- **Save paths and emulator knowledge.** That is sigil's territory and the client's.
- **Server-side policy.** The spec works against today's RomM API with a client-held baseline. A future server-side per-device baseline content hash would add an input source (a baseline that survives reinstalls), not new rules.

## Status

Early — extraction in progress. The rules come from a production implementation ([decky-romm-sync](https://github.com/danielcopper/decky-romm-sync)) that has been through a fair number of real conflict edge cases: baseline drift vs byte-identical restores, corrupt/truncated locals, both-sides-moved divergence, and stale-snapshot upload races.
