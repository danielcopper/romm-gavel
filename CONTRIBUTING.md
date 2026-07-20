# Contributing

gavel is a contract, so contributions follow one rule everything else derives from: **the vectors are the normative
artifact**. Prose explains, vectors decide — and implementations conform to vectors, never the other way around.

## The iron rule

**Never edit a vector to make an implementation pass.** A failing vector means either the implementation is wrong (fix
it there) or the contract itself is being changed. Changing the contract is legitimate — but it happens deliberately, in
a PR that says so, never as a test fix.

What a vector change means for consumers, and therefore for versioning:

| Change                                                         | Meaning                     | Version bump                                       |
| -------------------------------------------------------------- | --------------------------- | -------------------------------------------------- |
| An **existing** vector's `expected` value changes              | the contract itself changed | **major** — commit as `feat!:` / `BREAKING CHANGE` |
| New vectors or a new family are added                          | the contract grew           | **minor** — `feat:`                                |
| A vector's `name`/`rationale`, prose, tooling, reference, core | no contract change          | `docs:` / `chore:` / `ci:` / `fix:` as appropriate |

Clients vendor the vector files and pin a release — a changed `expected` value turns their CI red. That is the point
(silent contract drift is what gavel exists to prevent), which is exactly why it must surface as a major version, not
slip through a patch.

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

- **Vendor the vector families you conform to at a release tag**, not at a raw commit — copy the JSON into your repo and
  record the tag next to it. Updating is a deliberate re-copy plus tag bump, reviewed as a diff in _your_ repo.
- **Verify the core artifact by checksum.** Releases carry `libgavel-<arch>.so` plus its `.sha256`; pin the checksum on
  your side and re-verify in CI, so a swapped binary can never ship silently.
- **After a bump, re-run your conformance tests before anything else.** A major bump means at least one expected outcome
  changed — your implementation (or your vendored core) needs a matching change, and your own tests are what prove you
  made it.
