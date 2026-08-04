# Contributing

gavel is a contract, so contributions follow one rule everything else derives from: **the vectors are the normative
artifact**. Prose explains, vectors decide — and implementations conform to vectors, never the other way around.

## The iron rule

**Never edit a vector to make an implementation pass.** A failing vector means either the implementation is wrong (fix
it there) or the contract itself is being changed. Changing the contract is legitimate — but it happens deliberately, in
a PR that says so, never as a test fix.

What a change means for consumers, and therefore for versioning. Two surfaces are promised — the contract and the C ABI
— and either breaking is a major (see [What a release promises](SPEC.md#what-a-release-promises)):

| Change                                                          | Meaning                     | Version bump                                       |
| --------------------------------------------------------------- | --------------------------- | -------------------------------------------------- |
| An **existing** vector's `expected` value changes               | the contract itself changed | **major** — commit as `feat!:` / `BREAKING CHANGE` |
| A promised struct layout, signature or enumerator value changes | the C ABI broke             | **major** — `feat!:` / `BREAKING CHANGE`           |
| New vectors, a new family, or a new exported function           | the surface grew            | **minor** — `feat:`                                |
| A vector's `name`/`rationale`, prose, tooling, reference        | no promised surface changed | `docs:` / `chore:` / `ci:` / `fix:` as appropriate |

Adding a field to an existing struct belongs in the first two rows, not the third: it moves every field after it, so a
consumer's compiled copy reads garbage even though nothing was removed.

Clients vendor the vector files and pin a release — a changed `expected` value turns their CI red. That is the point
(silent contract drift is what gavel exists to prevent), which is exactly why it must surface as a major version, not
slip through a patch.

## What lives where, and why

Four directories carry the contract, and it is easy to mistake one for another:

|                    |                                                                                                                                                                                                                                                     |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vectors/`         | The contract itself. Everything else is a candidate that either satisfies these or does not.                                                                                                                                                        |
| `core/`            | **The implementation that ships**, and what a client should reach for first. C99 behind a promised C ABI, freestanding and allocation-free.                                                                                                         |
| `bindings/python/` | A **consumer** of the core: ctypes, no decision logic of its own. What it shows a client author is how to drive the ABI correctly.                                                                                                                  |
| `reference/`       | A **second implementation** in pure Python — not a consumer of the core, it never loads the `.so`. It exists so the vectors have a first consumer and so a port author has something readable to read. Outside the release promise: free to change. |

Two things follow from that split.

**An implementation is verified against the vectors, never against a sibling.** `core/tests` and `bindings/python/tests`
run the vectors and then test what only their own layer owns — ABI shapes for the core, marshalling for the binding.
Neither imports `reference/`. Comparing one candidate to another proves only that two things agree, which is not what
conformance means here.

**Breadth over the input space lives with the C drivers.** `core/tests/*_driver.c` walk the product of the inputs
against oracles transcribed from `SPEC.md`, under ASan and UBSan. That is where a sweep belongs: it runs against the
spec's reading, in the language the shipped code is written in, with the sanitizers watching.

## Process

- **PRs only** — `main` is protected; squash merges, the PR title becomes the commit (conventional-commit format,
  enforced by CI). [release-please](https://github.com/googleapis/release-please) turns merged commits into the next
  release PR; merging that cuts the tag, the CHANGELOG entry, and the compiled core artifacts.
- Every PR must keep the whole battery green: vector-shape validation (`scripts/validate_vectors.py`), the reference and
  core conformance runs, sanitizers, and formatting. Locally that is `mise run test`, `mise run sanitize`,
  `mise run validate` (see `mise.toml` for the toolchain — zig serves as the C compiler).
- New or changed vectors must pass the shape validator AND be adjudicated: state in the PR how the expected outcomes
  were derived (for extraction-based vectors, the production-kernel oracle; for spec-first vectors, the spec section
  they pin down).
- Formatting is mechanical, not debated: `deno fmt` for Markdown, `clang-format` (repo config) for C, rustfmt-style
  defaults for anything that grows later.

## Consuming a version (for client authors)

### Take the compiled core

This is the normal way, and it is what the repo is for. You do not implement the contract — you link the implementation
that already satisfies it.

Vendor `libgavel-<arch>.so` from a release, pin the `.sha256` that ships beside it, and re-verify the checksum in your
CI so a swapped binary can never ship silently. Since `v1.0.0` the C ABI is promised as well, so a pinned release also
fixes the struct layouts, signatures and enumerator values you compile or marshal against.

**You do not run the vectors.** The core satisfies them by construction and upstream CI proves it on every change;
running them again tests upstream, not you. What is worth testing on your side is your own marshalling — see
[`bindings/python`](bindings/python) for what that layer has to get right.

The one limit: releases currently carry x86_64 Linux only.

### Or implement the contract yourself

For anyone the core cannot reach — another architecture, a language you do not want to write a binding for, or an
implementation you already ship and intend to keep.

Vendor the vector families you conform to at a release tag, not at a raw commit: copy the JSON into your repo and record
the tag next to it. Updating is a deliberate re-copy plus tag bump, reviewed as a diff in _your_ repo. Record **which
families** you conform to, not just which release you pinned — the version number is repo-wide, the obligation is per
family (see [SPEC.md](SPEC.md#conformance)).

### After a bump, re-run your tests before anything else

A major release means one of the two promised surfaces broke, and which one decides what you have to do: a changed
`expected` needs a matching change in your implementation, a changed struct layout or signature needs a rebuild against
the new header. The changelog says which.

### What decky-romm-sync does, since it comes up

It takes the core, and nothing else: both save-sync decisions are answered by the compiled library in production, loaded
at bootstrap, with no Python fallback — a core that cannot load leaves the plugin inert on purpose.

It also vendors the vectors, but **not for conformance**. It kept its own former implementation as a test-only oracle,
and the vectors run against both so the two cannot drift apart unnoticed. That is a decision about its test suite, not a
second way of consuming gavel.
