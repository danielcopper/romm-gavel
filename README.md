<div align="center">

<img src="assets/logo-animated.gif" alt="romm-gavel" width="180">

# romm-gavel

<h3>What a save-sync client does after the server's verdict — decided once, for every client</h3>

[Spec](SPEC.md) · [Conformance](SPEC.md#conformance) · [Vectors](vectors/README.md) · [C core](core/gavel.h)

[Python binding](bindings/python) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

<a href="SPEC.md"><img alt="Spec" src="https://img.shields.io/badge/spec-read-4fa596?style=for-the-badge&labelColor=231710"></a>
<a href="https://github.com/danielcopper/romm-gavel/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/danielcopper/romm-gavel?style=for-the-badge&label=release&color=4fa596&labelColor=231710"></a>
<a href="https://github.com/danielcopper/romm-gavel/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/danielcopper/romm-gavel?style=for-the-badge&color=4fa596&labelColor=231710"></a>
<a href="core/gavel.h"><img alt="Core: C99, no libc" src="https://img.shields.io/badge/core-C99%2C%20no%20libc-4fa596?style=for-the-badge&labelColor=231710"></a>
<a href="https://github.com/danielcopper/romm-gavel/releases"><img alt="Platform: x86_64 Linux" src="https://img.shields.io/badge/platform-x86__64%20Linux-4fa596?style=for-the-badge&labelColor=231710"></a>

</div>

The client companion contract for RomM Device Sync — the layer the server hands to clients, written down as a spec
instead of re-guessed per client. It ships three ways: as a normative spec, as language-neutral conformance vectors, and
as a freestanding C99 core that already satisfies them.

_Vectors are the normative artifact: prose explains, vectors decide._

> **Covers saves, not save states.** The contract's inputs are a server-stamped `content_hash`, a per-device sync record
> and a slot. RomM gives saves all three and save states none of them, so save states become a consumer when the server
> gives them the same treatment, not before ([#20](https://github.com/danielcopper/romm-gavel/issues/20)). Releases
> currently carry x86_64 Linux only.

---

> [!NOTE]
> **How this is built.** The code is written by an AI coding agent working under my direction. The architecture, the
> design decisions and the review are mine, and every change is proven against the conformance vectors — reference,
> native core and binding alike — before it ships.

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
and what will its save be called"_, [atlas](https://github.com/danielcopper/emu-atlas) answers where the save lives, and
gavel answers what a client does in the space the server hands back.

The rules are not save-specific in principle — they compare content hashes, not file meaning. In practice they cover
saves and only saves, because that is what RomM stamps: a save carries a server `content_hash`, a slot and a per-device
sync record, and a save state carries none of the three. Without them the identity check has nothing on the server side
to compare against, and every decision falls through to the timestamp comparison — the weakest path in the table, as the
only path.

## What lives here

1. **[`SPEC.md`](SPEC.md)** — the client-side contract: what a client records at each sync boundary (its own baseline
   hash plus the server-stamped hash), the identity check's two routes, the 409/conflict resolution ladder, overwrite
   discipline, and the safety invariants — uncertainty never counts as a match; never destroy the only copy; a corrupt
   or implausibly shrunken local never auto-uploads; force-overwrite only on an explicit user choice.
2. **[`vectors/`](vectors/README.md)** — language-neutral JSON conformance vectors: the 409/conflict resolution ladder
   and the full sync decision (`input → expected action`). **These decide.** Any implementation in any language can run
   them and prove it decides the same way; where an implementation and a vector disagree, the vector is right.
   [`vectors/README.md`](vectors/README.md) has the how-to for pointing your own implementation at them.
3. **[`core/`](core/gavel.h)** — **what most clients should take.** A native C99 core behind a C ABI: the identity
   check, the ladder, and the full sync decision, already satisfying every vector. Allocation-free and _freestanding_ —
   the compiled library imports nothing at all, not even libc, so it loads on any x86_64 Linux whatever the distro
   ships. Releases carry `libgavel-x86_64-linux.so` and its `.sha256`, and since `v1.0.0` the ABI itself is part of the
   promise.
4. **[`bindings/python/`](bindings/python)** — the official Python binding: a ctypes wrapper over the core, and the
   worked example of driving the ABI correctly.
5. **[`reference/`](reference)** — a pure-Python second implementation, extracted from decky-romm-sync's production
   kernel. It exists so the vectors have a first consumer and so a port author has something readable to read; it is not
   what you ship against, and it is deliberately outside the release promise.

Spec and vectors came first on purpose — they define what the core must do and prove it does it, rather than the core
becoming the de-facto contract.

## What the contract decides

- **Bookkeeping** (normative) — at each successful sync boundary the client records `last_sync_hash` (its own baseline),
  `last_sync_server_hash` (the server's value, stored verbatim) and `last_sync_local_size`. Recorded only at successful
  boundaries, never speculatively; a value that could not be obtained is recorded as absent, never as an empty string,
  because absent means unknown and unknown never proves anything.
- **The identity check** (normative) — _"is my local file byte-identical to that server save?"_, answered by two routes
  so a drift between the client's hashing and the server's scheme never silently breaks identity: **provenance** (local
  unchanged since the baseline, and that baseline synced against this exact server content) as the primary, **parity**
  (local hash equals the server's `content_hash` directly) as the fallback for a file with no sync history on this
  device. Every compared value must be present and non-empty.
- **The 409 resolution ladder** (normative) — automatic uploads POST with `overwrite=false`, and the server's 409 proves
  the slot's head moved past what this device last synced. The client re-decides from hashes alone: unchanged since
  baseline → download; byte-identical to the head → download; otherwise → conflict, surfaced to the user. Missing or
  empty information never yields download.
- **Overwrite discipline** (normative) — `overwrite=true` is sent only to execute an explicit user keep-local decision.
  No automatic path ever forces, and the client neither retries the POST unchanged nor escalates on its own.
- **The decision table** (informative) — the full per-`(rom, filename, slot)` model the reference client uses, for
  clients that compute detection themselves. Informative means "not required of every client", not "optional to get
  right": where the family applies, its vectors decide exactly as tightly as the ladder's.

## What does not live here

- **Detection.** negotiate owns "who changed" — this contract starts where the server's verdict ends. gavel is not a
  competing authority; it documents the client's side of the protocol.
- **Hashing schemes, file I/O, transport, UI.** The server's hash is authoritative; clients remember what the server
  said rather than recompute it. Local recomputation is at most a fallback for files a device has never synced.
- **Save paths and emulator knowledge.** That is sigil's and atlas's territory, and the client's.

## Consuming it

**Take the compiled core.** This is the normal way, and it is what the repo is for: you do not implement the contract,
you link the implementation that already satisfies it. Vendor `libgavel-x86_64-linux.so` from a release, pin the
`.sha256` that ships beside it, and re-verify the checksum in your CI so a swapped binary can never ship silently. You
do not run the vectors — the core satisfies them by construction and upstream CI proves it on every change. What is
worth testing on your side is your own marshalling; [`bindings/python`](bindings/python) shows what that layer has to
get right.

**Or implement the contract yourself**, for anyone the core cannot reach — another architecture, or a language you do
not want to write a binding for. Vendor the vector families you conform to at a release tag, not at a raw commit, and
record **which families** you conform to rather than only which release you pinned: the version number is repo-wide, the
obligation is per family.

Two surfaces are promised, and either one changing incompatibly is a major release: the contract (every vector's
`expected` value, plus the normative spec sections) and the C ABI in [`core/gavel.h`](core/gavel.h) — struct layouts,
signatures, enumerator values and the input conventions the header states. Adding vectors, a family, or an exported
function is a minor. Adding a field to an existing struct is not, because it moves the fields after it.
[`SPEC.md`](SPEC.md#what-a-release-promises) has the full list, including what is explicitly _not_ promised.

## When this becomes unnecessary — by design

If RomM grows a per-device baseline anchor and resolution directives on its verdicts, parts of this contract move
server-side and this repo shrinks accordingly. That is the goal, not a failure mode: the contract documents the current
client obligation precisely enough that upstreaming it is easy. Until then, three shipped clients resolving the same
slot state differently is the problem this solves.

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

## Contributing

```bash
mise run setup      # pinned test dependencies into the local venv
mise run build      # build the core as build/libgavel.so
mise run test       # every vector against the reference, the C core, and the Python binding
mise run sanitize   # the C drivers under ASan + UBSan
mise run validate   # vector shape validation
deno fmt --check
```

[`CONTRIBUTING.md`](CONTRIBUTING.md) carries the one rule everything else derives from — **never edit a vector to make
an implementation pass** — plus what a vector change means for versioning (a changed `expected` is a major bump, by
design) and how to consume a release as a client author.

[![CI](https://github.com/danielcopper/romm-gavel/actions/workflows/ci.yml/badge.svg)](https://github.com/danielcopper/romm-gavel/actions/workflows/ci.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)
[![Coverage](https://img.shields.io/sonar/coverage/danielcopper_romm-gavel?server=https%3A%2F%2Fsonarcloud.io)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)
[![Maintainability](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)
[![Reliability](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)
[![Security](https://sonarcloud.io/api/project_badges/measure?project=danielcopper_romm-gavel&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=danielcopper_romm-gavel)

## License

MIT. This is an independent project and is not affiliated with, endorsed by, or sponsored by the RomM project.
