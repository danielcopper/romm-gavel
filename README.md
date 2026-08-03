# romm-gavel

[![CI](https://github.com/danielcopper/romm-gavel/actions/workflows/ci.yml/badge.svg)](https://github.com/danielcopper/romm-gavel/actions/workflows/ci.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)
[![Security](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)
[![Reliability](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)
[![Maintainability](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=coverage)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)

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

The rules are not save-specific in principle — they compare content hashes, not file meaning. In practice they cover
saves and only saves, because that is what RomM stamps: a save carries a server `content_hash`, a slot and a per-device
sync record, and a save state carries none of the three. Without them the identity check has nothing on the server side
to compare against, so save states become a consumer when the server gives them the same treatment, not before
([#20](https://github.com/danielcopper/romm-gavel/issues/20)).

## What lives here

1. **`SPEC.md`** — the client-side contract: what a client records at each sync boundary (its own baseline hash plus the
   server-stamped hash), the 409/conflict resolution ladder, overwrite discipline, and the safety invariants
   (uncertainty never counts as a match; never destroy the only copy; a corrupt or implausibly shrunken local never
   auto-uploads; force-overwrite only on an explicit user choice).
2. **`vectors/`** — language-neutral JSON conformance vectors: the 409/conflict resolution ladder and the full sync
   decision (`input → expected action`). Any implementation in any language can run them and prove it decides the same
   way — [`vectors/README.md`](vectors/README.md) has the how-to for pointing your own implementation at them.
3. **`reference/`** — a pure-Python reference implementation, extracted from decky-romm-sync's production kernel.
4. **`core/`** — a native C99 core behind a C ABI, for clients that want a drop-in instead of maintaining their own
   implementation: the identity check, the ladder, and the full sync decision. Allocation-free and _freestanding_ — the
   compiled library imports nothing at all, not even libc, so it loads on any x86_64 Linux whatever the distro ships.
   Releases carry `libgavel-x86_64-linux.so` and its `.sha256`.
5. **`bindings/python/`** — the official Python binding: a ctypes wrapper over the core, mirroring the reference's
   signatures so a consumer swaps one import for the other.

Spec and vectors came first on purpose — they define what the core must do and prove it does it, rather than the core
becoming the de-facto contract.

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

## Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md) carries the one rule everything else derives from — **never edit a vector to make
an implementation pass** — plus what a vector change means for versioning (a changed `expected` is a major bump, by
design) and how to consume a release as a client author.

## Status

Both vector families exist and the contract is implemented twice over.

The 409 resolution ladder is extracted end-to-end: normative spec sections (bookkeeping, identity check, ladder,
overwrite discipline) and a curated plus exhaustive vector set under `vectors/ladder/`. The decision-table family
(`vectors/decision-table/`) covers the full informative decision model the same way — including the provenance identity
route the ladder vectors can't reach.

Every vector runs against the Python reference, the native core, and the Python binding on each PR, alongside
differentials between them and sanitizer sweeps over the C. The rules come from a production implementation
([decky-romm-sync](https://github.com/danielcopper/decky-romm-sync)) that has been through a fair number of real
conflict edge cases: baseline drift vs byte-identical restores, corrupt/truncated locals, both-sides-moved divergence,
and stale-snapshot upload races — and that now resolves its 409s through the compiled core, with no Python fallback.

Not here yet: bindings beyond Python, and release artifacts beyond x86_64 Linux. Both are tracked as open issues, and
both are waiting on a consumer rather than on the work — a binding nobody adopts is speculation.
