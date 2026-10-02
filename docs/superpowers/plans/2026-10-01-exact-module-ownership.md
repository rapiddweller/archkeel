# Exact Module Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Assign a package initializer to one existing component without assigning its descendants.

**Architecture:** Optional `exact_modules` uses equality; existing `packages` uses recursive prefix matching. One shared predicate counts components, not selectors. No precedence resolves conflicting claims. Projection preserves selector kinds through recursive evaluation and Actual/Target/Diff.

**Tech Stack:** Existing dataclasses, JSON schema, pathlib, pytest and browser acceptance; no dependencies.

**Spec:** `.superpowers/sdd/2026-10-01-exact-module-ownership/spec.md` (GitHub #211), to publish with the implemented feature as AD-128; Astra's full source audit remains in the CE artifact `test-artifacts/archkeel-exact-module-design-astra.md`.

## Global Constraints

- `exact_modules` is a unique array of dotted identifiers; malformed/null values are rejected.
- Omitted and empty normalize to `None`; old canonical bytes and digests stay identical.
- Keep required `packages`; `[]` is valid only with nonempty exact ownership. `namespace` retains its existing package-placement meaning.
- Equality and prefix claims have equal standing. Overlap within one component counts once; competing components remain ambiguous.
- Ownership does not grant public access, scan completeness, or recursive child ownership.
- Nonempty ownership changes require existing digest-bound amendments.
- Python and Dart module identity semantics are retained; no new Dart support claims.
- Controller alone commits after independent QA, root review and Astra review.

## Review Focus

- Executable mount-root initializers stay visible and owned without absorbing siblings.
- Child recursive claims cannot escape an exact-only parent.
- Missing exact names are not satisfied by same-prefix descendants or a partial scan.
- Existing contracts, ownership ambiguity, dependency shorthand and widening remain compatible.
- Target works with no source; reconstructed observation ownership agrees with evaluator ownership at every depth.

## Task 1: Precise ownership through the existing pipeline

**Files:**
- Model/codec/schema: `src/archkeel/ir/model.py`, `ir/codec.py`, `schema/architecture-contract.schema.json`.
- Evaluation/projection: `src/archkeel/analyzer/embedded/scanner.py`, `violations.py`, `contract.py`, `dependencies.py`; `src/archkeel/check/validation.py`.
- Consumers: `src/archkeel/ir/interfaces.py`, `levels.py`, `decisions.py`; `src/archkeel/render/flow.py`, `html.py`; `src/archkeel/check/onboarding.py`.
- QA: new `tests/test_exact_module_ownership.py`, reusing existing fixture helpers; existing widening/rename and browser tests only where needed.
- Documentation: existing reference, rules, release notes and architecture demo catalog; one concise decision record.

**Interfaces:**
- Append `ContractComponent.exact_modules: tuple[str, ...] | None = None`.
- Shared `component_owns_module(component: ContractComponent, module: str) -> bool` implements equality OR existing prefix ownership.
- Component observation records retain recursive packages in `subjects`, with nonempty exact claims in `data.exact_modules`. Reconstructed owners keep the two kinds separate.
- Parent recursive claims admit contained child recursive/exact claims; parent exact claims admit only equal child exact claims.

- [ ] Independent Luna QA first tests codec/default digests, unique ownership, exact-only components, two-depth scope clipping, missing/partial scans, sibling isolation, retained forbidden-import/cycle/type failures, observation reconstruction, source-free Target, amendments/rename, and existing Dart unsupported boundaries.
- [ ] Run the new tests on the reviewed bugfix baseline. Verify failures are absent-feature failures, not test mistakes.
- [ ] Independent Luna implementation adds the field and shared predicate, then audits every direct package-ownership consumer. Do not turn exact claims into prefixes or drop outside-parent declarations.
- [ ] Run focused tests; review diff for canonical-byte drift and formerly silent ownership paths. Independent QA extends negative cases without seeing implementer's proposed reasoning on its first pass.
- [ ] Run `UV_NO_CONFIG=true make check`, `make self-observation`, `make gate`, and `make report-browser`. Validate the CE task-root contract probe with the candidate without editing CE to obtain a pass.
- [ ] Astra reviews the frozen diff and evidence. Controller commits only the coherent feature, then opens/updates the tooling PR with examples and honest limits.

Release follows merged CI and verified isolated package installation. Only then pin CE to the release and migrate explicit ownership; no CE completion claim follows from tooling alone.
