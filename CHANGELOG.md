# Changelog

## [2.0.0](https://github.com/danielcopper/romm-gavel/compare/v1.0.1...v2.0.0) (2026-10-22)


### ⚠ BREAKING CHANGES

* **core:** The C ABI struct gavel_local_file gains two fields, appended after the existing ones: int size_fixed and int has_size_fixed. The struct changes size, so the core reads past the end of one built against the old layout; a caller must rebuild and clear has_size_fixed where it does not know whether the file's size is fixed. size_fixed is nonzero when the hardware or the format fixes the file's size, so the file never legitimately loses content; it can get shorter only by dropping trailing fill. For such a file the corrupt-local guard also answers a conflict when the local raw size is below the content size recorded at the last sync, or below the recorded raw size where no content size is recorded; the 0-byte rule and the half rule still apply to every file. SPEC.md defines the fact normatively under Inputs. The decision-table vectors gain an optional input key, local_file.size_fixed (true or false, absent when unknown), which a port must read to pass the new vectors; no expected value changed and no vector was renamed. The Python binding reads the key from its dict input and refuses any value other than True, False or None (unknown).
* **core:** The C ABI structs gavel_local_file and gavel_bookkeeping gain fields, appended after the existing ones: int64_t content_size and int has_content_size on gavel_local_file, int64_t last_sync_content_size and int has_last_sync_content_size on gavel_bookkeeping. Both structs change size, so the core reads past the end of a struct built against the old layout; a caller must rebuild and clear the new flags where it states no content size. The content size is a file's size less the trailing run of the byte it ends with, when that byte is 0xFF or 0x00. The corrupt-local guard compares the two content sizes with the same half rule where both are given, and decides as before where either is absent; a raw size of 0 is still refused. SPEC.md defines the content size normatively under Inputs, and its Bookkeeping section gains last_sync_content_size. The decision-table vectors gain two optional input keys, local_file.content_size and files_state.last_sync_content_size, which a port must read to pass the new vectors; no expected value changed and no vector was renamed. The Python binding reads both keys from its dict inputs.
* **core:** In the decision table, a device not current on the slot's head (is_current=false) with a local file present that the identity check proves byte-identical to the head no longer gets download with server_save_id; it gets skip with reason synced, adopt_baseline, server_save_id set to the head's id and acknowledge set. This holds with no last_sync_hash, with one the local file diverged from, and with one it is unchanged since. Every skip with adopt_baseline now carries server_save_id (the chosen head's id, where it used to be 0) and acknowledge (true only in that is_current=false case, false for the adoptions in the is_current=true and no-entry branches); in the vectors' expected both keys are present on every adopting skip and absent on any other skip. The C ABI struct gavel_sync_action gains a final field, int acknowledge, after server_save_id, which changes its size: a caller compiled against the old layout passes a buffer too small for the core to write. Changed expected: moved-past-no-baseline-parity, moved-past-diverged-identical, current-no-baseline-parity, never-synced-parity-dedup and never-synced-provenance-dedup. No vector was renamed. SPEC.md's normative Bookkeeping section gains two client obligations: a client that adopts a head its device is not current on acknowledges it to the server as synced, and records the new baseline only after that acknowledgement succeeded. New vectors expecting the adoption: moved-past-unchanged-provenance, moved-past-unchanged-parity. The Python binding's result gains the same two keys on an adopting skip.
* **core:** In the decision table, a device that is current on the slot's head (is_current=true) with a local file present and no last_sync_hash recorded no longer always gets skip with adopt_baseline. It gets skip with adopt_baseline only when the local file is byte-identical to the head (local hash equals the head's content_hash); otherwise, including a head without content_hash or an unknown local hash, it gets conflict with server_save_id set to the head's id. The vector current-no-baseline-adopts keeps its input as current-no-baseline-different.

### Features

* **core:** guard fixed-size saves against any shrink ([#60](https://github.com/danielcopper/romm-gavel/issues/60)) ([eb84ac8](https://github.com/danielcopper/romm-gavel/commit/eb84ac836afe7445174c26dbdd0b6d62ddae620d))


### Bug Fixes

* **core:** adopt an identical local when the device is not current ([#58](https://github.com/danielcopper/romm-gavel/issues/58)) ([dd1b4c0](https://github.com/danielcopper/romm-gavel/commit/dd1b4c09535c49d93fc0fabe721db4374bca12a6))
* **core:** compare content sizes in the corrupt-local guard ([#59](https://github.com/danielcopper/romm-gavel/issues/59)) ([33007e8](https://github.com/danielcopper/romm-gavel/commit/33007e86030d6d0e2b3f96f37e0f7dd0887a3d36))
* **core:** decide a baseline-less local on a current head by identity ([#54](https://github.com/danielcopper/romm-gavel/issues/54)) ([864fb54](https://github.com/danielcopper/romm-gavel/commit/864fb54ce8c5c0281f3dd956ba053ddea82839bb))

## [1.0.1](https://github.com/danielcopper/romm-gavel/compare/v1.0.0...v1.0.1) (2026-08-04)


### Bug Fixes

* rebuild the base ref rather than pass it through, declare CI permissions ([#35](https://github.com/danielcopper/romm-gavel/issues/35)) ([2599a55](https://github.com/danielcopper/romm-gavel/commit/2599a55e43549b2ce86519f7dd075abc8c25620c))
* **scripts:** validate the base ref, and flatten the expected-shape check ([#31](https://github.com/danielcopper/romm-gavel/issues/31)) ([8044456](https://github.com/danielcopper/romm-gavel/commit/80444564e45be2e1cb7bf8538a5fe9b79f050dda))

## [1.0.0](https://github.com/danielcopper/romm-gavel/compare/v0.4.0...v1.0.0) (2026-08-03)


### Features

* declare the contract and the C ABI stable ([#28](https://github.com/danielcopper/romm-gavel/issues/28)) ([ef6b8b5](https://github.com/danielcopper/romm-gavel/commit/ef6b8b580c99665db1177f8c1d582a503afccdfa))

## [0.4.0](https://github.com/danielcopper/romm-gavel/compare/v0.3.0...v0.4.0) (2026-08-03)


### Features

* extend the native core to the full sync decision ([#21](https://github.com/danielcopper/romm-gavel/issues/21)) ([f477794](https://github.com/danielcopper/romm-gavel/commit/f477794b3a66f868377665d0fa205274bd4ac4b3)), closes [#5](https://github.com/danielcopper/romm-gavel/issues/5)

## [0.3.0](https://github.com/danielcopper/romm-gavel/compare/v0.2.0...v0.3.0) (2026-07-20)


### Features

* make the core freestanding — zero library dependencies ([#16](https://github.com/danielcopper/romm-gavel/issues/16)) ([33a36ae](https://github.com/danielcopper/romm-gavel/commit/33a36aed554fe85c38b418f45cc936044c0ddbe4))

## [0.2.0](https://github.com/danielcopper/romm-gavel/compare/v0.1.0...v0.2.0) (2026-07-20)


### Features

* official python binding for the native core ([#13](https://github.com/danielcopper/romm-gavel/issues/13)) ([4a969a7](https://github.com/danielcopper/romm-gavel/commit/4a969a7059b4bff7361932494cc8cdea4eb2749d))

## 0.1.0 (2026-07-20)


### Features

* add the decision-table vector family with a reference port of the full sync decision ([195e43b](https://github.com/danielcopper/romm-gavel/commit/195e43bf7b249974634fd0480239076379a401aa))
* extract the 409 resolution ladder — spec, conformance vectors, reference implementation ([b2e550b](https://github.com/danielcopper/romm-gavel/commit/b2e550b03b80d5cb28b859cc20c34fecf52c0f5f))
* native core — resolve_upload_conflict behind a C ABI ([#11](https://github.com/danielcopper/romm-gavel/issues/11)) ([f57f2e8](https://github.com/danielcopper/romm-gavel/commit/f57f2e8e78959220a66cd1f1f6cb04bf6fc9898e))
