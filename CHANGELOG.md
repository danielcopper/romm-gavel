# Changelog

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
