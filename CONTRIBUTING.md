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
| `reference/`       | A **second implementation** in pure Python — not a consumer of the core, it never loads the `.so`. It exists so the vectors have a first consumer and so a port author has something readable to read. Outside the release promise: free to change. |
| `core/`            | The implementation that ships. C99 behind a C ABI, freestanding and allocation-free.                                                                                                                                                                |
| `bindings/python/` | A **consumer** of the core: ctypes, no decision logic of its own. It is what shows a client author how to drive the ABI correctly.                                                                                                                  |

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

There are two ways to consume gavel, and a release gives them different things.

**If you implement the contract yourself**, vendor the vector families you conform to at a release tag, not at a raw
commit — copy the JSON into your repo and record the tag next to it. Updating is a deliberate re-copy plus tag bump,
reviewed as a diff in _your_ repo. Record **which families** you conform to, not just which release you pinned: the
version number is repo-wide, the obligation is per family (see [SPEC.md](SPEC.md#conformance)).

**If you vendor the compiled core**, the vectors are not yours to run — the core already conforms and its CI proves that
on every change. What you need is the artifact and its checksum: releases carry `libgavel-<arch>.so` plus its `.sha256`;
pin the checksum on your side and re-verify in CI, so a swapped binary can never ship silently. Since `v1.0.0` the C ABI
is part of the promise, so a pinned release also fixes the struct layouts and signatures you compile or marshal against.

Doing both is reasonable if you keep your own implementation as a differential oracle — that is what
[decky-romm-sync](https://github.com/danielcopper/decky-romm-sync) does: the core decides in production, the in-tree
kernel survives only in tests, and the vendored vectors run against both so the two can never drift apart unnoticed.

**After a bump, re-run your tests before anything else.** A major release means one of the two promised surfaces broke,
and which one decides what you have to do: a changed `expected` needs a matching change in your implementation, a
changed struct layout or signature needs a rebuild against the new header. The changelog says which.
