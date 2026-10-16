# Exact module-object grants implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement these steps with native remote GitHub verification.

**Goal:** Implement issue #544: permit one exact caller to import one exact module object without publishing additional symbols.

**Architecture:** Add frozen `ModuleObjectGrant(source_module: str, target_module: str)` values to `InterfaceBoundaryRule.module_object_grants`, optional with `None` preserving historical bytes and `()` preserving authored empty arrays. Contract 3.6 gates the new field. The interface evaluator admits only proven module-object imports; the existing component `public` inventory and all other policies remain authoritative.

**Tech Stack:** Python 3.11, frozen dataclasses, JSON Schema, pytest; remote Git objects and hosted Actions only.

**Spec:** https://github.com/rapiddweller/archkeel/issues/544 and the authorized exact-module design.

## Constraints and review focus

- Exact source/target identities only; no prefixes, symbol names, inferred grants or second API inventory.
- Named/private/wildcard imports and same-owner forwarder leaks remain governed by existing public declarations.
- Relative and aliased imports must use resolved identities; unknown symbol facts never qualify.
- Complete requires, forbidden dependencies and invalid export checks retain authority; dynamic attribute use is outside this proof.
- Old versions reject the new field; absent and empty have distinct canonical encodings; nested module references support validation, mounted contracts, rename and widening.
- Preserve own baseline ceilings and named publication; no blanket allowances.

## Task 1: Native evaluator behavior

- [x] Add `tests/test_module_object_grants.py` using actual disposable Python repositories and normal observation/evaluation. Pin exact caller/target, absolute/relative/alias positives, ungranted caller/target and named/private/wildcard/forwarder negatives, public names, unknown facts and other-policy controls.
- [x] Run the tests on the unchanged base and record RED for the missing grammar/permission.
- [x] Add the typed model and narrow evaluation branch; preserve the existing named import path.
- [x] Run native controls and relevant interface/decision regressions to GREEN.

## Task 2: Contract lifecycle

- [x] Add failing tests for strict grant shape/FQN/duplicates, schema-version gating, absent/empty roundtrips, declaration-record decoding, nested references/rename, mounted evaluation, and grant widening/removal.
- [x] Add 3.6 schema and version maps following 3.5 patterns, strict codec, module-reference traversal, declaration projection and widening comparison. Publish the one model type through existing named seams only when required by actual use.
- [x] Run codec/schema/version/reference/rename/widening/profile regressions and fix only relevant failures.

## Task 3: Documentation and verification

- [x] Document 3.6 JSON syntax, exact module-object semantics, unchanged named API inventory and dynamic-use limit; update required schema listings and focused test entry.
- [x] Run hosted formatting (capture and commit any patch), Ruff, mypy, repository hygiene, focused regressions, and full-source own validation against unchanged baseline.
- [x] Produce a clean commit without temporary workflows; parent arranges full-suite verification, normal amendment if necessary, independent Astra review and PR integration.

## Verification record

- Native policy RED: [38929456957](https://github.com/rapiddweller/archkeel/actions/runs/38929456957), after the new grammar passed and before the permission branch.
- Native/lifecycle controls: 56 passed; focused existing regressions: 566 passed.
- Full lint, mypy (138 source files), all 11 hygiene checks and reproducible schemas passed.
- Final native own validation: [38933763819](https://github.com/rapiddweller/archkeel/actions/runs/38933763819), 132/132 files, 919 unresolved calls, 65 unknown positions, zero violations.
- The standard eight-entity Target amendment validates against the clean combined base in [38933327926](https://github.com/rapiddweller/archkeel/actions/runs/38933327926), with identical baseline digests.

Parent coordination retains the full combined suite, independent Astra review and PR integration.


## Integration on the State and observer chain

The feature retains real ancestry through predecessor `61404f1cf9e8579929119be093c3676075754661`; all 25 State Target entities and the suite corrections remain intact. The product tree contains no temporary workflow.

- Integrated checks: [38938213642](https://github.com/rapiddweller/archkeel/actions/runs/38938213642), 287 tests passed, full lint, mypy (138 source files), hygiene and schema reproduction passed.
- Integrated own validation and fresh standard amendment against that exact predecessor: [38938140826](https://github.com/rapiddweller/archkeel/actions/runs/38938140826), both commands exit 0, 919 unresolved calls, 65 unknown positions, zero violations and identical baseline digests.
- The generated amendment replaces the earlier combined-base amendment. No grants, publication, exceptions or baseline ceilings were added to the own contracts. Independent final review remains with the parent.
