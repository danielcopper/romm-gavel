# romm-gavel

The client companion contract for RomM Device Sync — the layer the server hands to clients, written down as a spec
instead of re-guessed per client.

## Why

RomM's Device Sync deliberately splits the work. The server owns **hashing** (it stamps every save's `content_hash` and
expects clients to remember it) and **detection** (negotiate returns upload/download/conflict verdicts). What it hands
back to the client is everything _after_ a verdict: what to record at each sync boundary, what to do with a 409, and
when a conflict must reach the user. There is no resolve endpoint and no server-side resolution policy — RomM's own sync
modes quarantine conflicting files and notify, they never pick a winner.

Today at least three clients (Argosy, Grout, decky-romm-sync) have independently invented that layer — a local baseline
hash, a remembered server hash, a "local provably unchanged, so just download" downgrade, force-overwrite only on an
explicit user choice — but with different edges. The same slot state can resolve three different ways depending on which
client touches it.

gavel writes that delegated layer down. [sigil](https://github.com/rommforge/argosy-sigil) answers _"which game is this
and what will its save be called"_ — gavel answers what a client does in the space the server hands back.

The rules are not save-specific either: anything RomM syncs as a local-file-vs-server-version pair gets the same
contract — saves today, save states as the natural next consumer.

## What lives here

1. **`SPEC.md`** — the client-side contract: what a client records at each sync boundary (its own baseline hash plus the
   server-stamped hash), the 409/conflict resolution ladder, overwrite discipline, and the safety invariants
   (uncertainty never counts as a match; never destroy the only copy; a corrupt or implausibly shrunken local never
   auto-uploads; force-overwrite only on an explicit user choice).
2. **`vectors/`** — language-neutral JSON conformance vectors, starting with the 409/conflict resolution ladder
   (`input → expected action`). Any implementation in any language can run them and prove it decides the same way.
3. **`reference/`** — a pure-Python reference implementation, extracted from decky-romm-sync's production kernel.
4. **Planned: a native core** with a C ABI plus per-language bindings (sigil-style), for clients that want a drop-in
   instead of maintaining their own implementation. Spec and vectors come first — they define what the core must do and
   prove it does it.

## What does not live here

- **Detection.** negotiate owns "who changed" — this contract starts where the server's verdict ends. gavel is not a
  competing authority; it documents the client's side of the protocol.
- **Hashing schemes, file I/O, transport, UI.** The server's hash is authoritative; clients remember what the server
  said rather than recompute it. Local recomputation is at most a fallback for files a device has never synced.
- **Save paths and emulator knowledge.** That is sigil's territory and the client's.

## When this becomes unnecessary — by design

If RomM grows a per-device baseline anchor and resolution directives on its verdicts, parts of this contract move
server-side and this repo shrinks accordingly. That is the goal, not a failure mode: the contract documents the current
client obligation precisely enough that upstreaming it is easy. Until then, three shipped clients resolving the same
slot state differently is the problem this solves.

## Status

Early — extraction in progress. The rules come from a production implementation
([decky-romm-sync](https://github.com/danielcopper/decky-romm-sync)) that has been through a fair number of real
conflict edge cases: baseline drift vs byte-identical restores, corrupt/truncated locals, both-sides-moved divergence,
and stale-snapshot upload races.
