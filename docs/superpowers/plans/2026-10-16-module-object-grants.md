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

- [ ] Add `tests/test_module_object_grants.py` using actual disposable Python repositories and normal observation/evaluation. Pin exact caller/target, absolute/relative/alias positives, ungranted caller/target and named/private/wildcard/forwarder negatives, public names, unknown facts and other-policy controls.
- [ ] Run the tests on the unchanged base and record RED for the missing grammar/permission.
- [ ] Add the typed model and narrow evaluation branch; preserve the existing named import path.
- [ ] Run native controls and relevant interface/decision regressions to GREEN.

## Task 2: Contract lifecycle

- [ ] Add failing tests for strict grant shape/FQN/duplicates, schema-version gating, absent/empty roundtrips, declaration-record decoding, nested references/rename, mounted evaluation, and grant widening/removal.
- [ ] Add 3.6 schema and version maps following 3.5 patterns, strict codec, module-reference traversal, declaration projection and widening comparison. Publish the one model type through existing named seams only when required by actual use.
- [ ] Run codec/schema/version/reference/rename/widening/profile regressions and fix only relevant failures.

## Task 3: Documentation and verification

- [ ] Document 3.6 JSON syntax, exact module-object semantics, unchanged named API inventory and dynamic-use limit; update required schema listings and focused test entry.
- [ ] Run hosted formatting (capture and commit any patch), Ruff, mypy, repository hygiene, focused regressions, and full-source own validation against unchanged baseline.
- [ ] Produce a clean commit without temporary workflows; parent arranges full-suite verification, normal amendment if necessary, independent Astra review and PR integration.
