# Atlas deviation boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Give the existing Atlas deviation producer and real scene consumer one precise, wire-compatible value boundary.

**Architecture:** Extract the actual pair-difference derivation and immutable value from the 829-line Atlas packer into a small cohesive owner. Generate its two browser values from that Python Enum, decode the concrete rows once, and let one checked classic-JS consumer classify the pairs used by atlasScene.

**Tech Stack:** Python 3.11+, existing TypeScript 5.9.3/checkJs generator, pytest/Chromium, native Archkeel guards.

**Spec:** docs/superpowers/specs/2026-10-16-atlas-deviation-boundary.md

## Global Constraints

- At most 160 new manual production lines; generated artifacts, moved existing logic and tests/docs are reported separately.
- No any, casts, ignores, new compiler/bundler/cache framework, graph copy or second spelling registry.
- Preserve five wire fields and their order, stable IDs, sorted pair order, empty/missing deviations, input immutability and existing public Scene APIs.
- Open IDs, names, actors and layers stay strings; PermissionStatus and other Atlas/UI control domains remain pending.
- No allowance/budget increase, historical JSON snapshots or whole-Atlas/browser absence claim.

## Review Focus

- Root and nested levels with identical component pairs must remain distinct.
- Empty or missing deviation arrays must preserve the old valid Scene API; malformed supplied rows must reject.
- Zero, unknown strings and another nominal domain must not become valid kinds.
- Shared declared/used pairs must produce no deviation, with deterministic output independent of set iteration order.
- The actual dict facade must keep plain string kinds, JSON key order and IDs; one clone/one ingress decode must suffice for repeated projections.

## Task 1: Pin real ingress and typed producer REDs

**Files:** tests/test_atlas_deviation_boundary.py; tests/test_atlas_deviation_target.py; this spec/plan.

**Interfaces:** Test the actual ArchkeelReportScene.create(data) and planned level_deviations(level_id, declared, used) boundary; independent target pins AtlasDeviation.kind and its producer return.

- [ ] Add actual public Scene tests using the existing packed-Atlas fixture shape: unsupported kind, numeric source ID and numeric level ID must reject TypeError. Keep valid empty and omitted arrays as passing controls.
- [ ] Add a producer test for sorted allowed_unused then undeclared pairs, equal/shared pairs, plain five-field wire dictionaries, stable IDs and two independent levels.
- [ ] Add fixed native intent for the actual new DTO kind and level_deviations return; observe the absent/legacy source mismatch before production.
- [ ] Run RED on unchanged production; record exact assertion/mismatch evidence and commit tests independently.

## Task 2: Close the actual deviation value and consumer

**Files:** src/archkeel/render/atlas_deviations.py (new); atlas.py; assets/report-graph-protocol.ts; assets/report-atlas-deviations.js (new); assets/report-scene.js; tools/browser_graph_protocol.py; generated vocabulary/protocol; html.py; Makefile; dependency loaders/ship checks; authored render contract.

**Interfaces:**
- Python AtlasDeviationKind; frozen AtlasDeviation; level_deviations(level_id: str | None, declared: set[tuple[str, str]], used: set[tuple[str, str]]) -> tuple[AtlasDeviation, ...]; AtlasDeviation.to_wire() -> dict[str, str | None].
- Protocol AtlasDeviation five-field interface with canonical generated kind; decodeAtlasDeviations(value: unknown) -> AtlasDeviation[] preserving original list/row identity.
- ArchkeelAtlasDeviations.create(value: unknown) -> DeviationIndex with isUndeclared(levelId, sourceId, targetId): boolean and unused(levelId): readonly AtlasDeviation[].

- [ ] Implement the Python value/real derivation; delegate from _level_balance, use attributes in _atlas_levels, and emit existing dicts only at atlas_payload.
- [ ] Register the actual Enum with the existing generator and add the precise predicate using existing primitive validators; reject unsupported input without a broad cast.
- [ ] Implement the checked browser level/pair index, constructed once from the existing cloned Atlas. Replace the actual atlasScene kind decisions with its operations and retain original source/target IDs instead of splitting pair strings.
- [ ] Add the new authored JS asset in the real HTML/fixture/packaging load order and existing strict compiler target; regenerate only through the existing official command.
- [ ] Count manual source before committing; if above 160 lines, narrow the stage. Run Task1 GREEN and commit the minimal production boundary.

## Task 3: Verify independent type and source controls

**Files:** tests/test_atlas_deviation_boundary.py; tests/test_atlas_deviation_target.py; tests/browser_graph_scene_target.ts; CI routing/gates only where required.

- [ ] Under fixed authored Python intent, mutate the actual kind annotation and producer return to str/broad data; require trace-valid native FAIL. Add raw equality/membership/alias controls and a valid data/Enum control for the whole new Python owner.
- [ ] Mutate the actual checked JS unused-row return to project a raw kind and a foreign nominal kind; widen its return under the fixed authored compiler target. Require genuine compiler diagnostics. Enum-versus-literal equality is not a compiler rejection claim; its separate native witness is the next step.
- [ ] Run the actual TypeScript/JS collector on one written-literal consumer mutation and require a trace-valid forbidden_construct FAIL while capability remains PARTIAL.
- [ ] Verify unknown decoding, same row identity, unchanged complete wire JSON and repeated projections; compare actual old/new Atlas scenes and Mermaid for root/nested Diagram/Target/Diff plus the existing Evidence modes.
- [ ] Run the unmodified required report Make path, appropriate Atlas/renderer Chromium tests, deterministic/stale artifact checks, wheel/sdist offline shipping and unchanged 2MB/400KB guards on the actual combined Publisher basis.
- [ ] Record source/generated costs and any real native site deltas. Obtain independent Astra review; Root integrates with an exact predecessor and normal amendment.

## Handoff

Plan-only predecessor is frozen Scene 0aee692. No Atlas production is changed yet. Publisher/Main refs remain exclusively with the integration steward. Task1 RED precedes Task2, and Root reviews source cost before production commit.

## Task 1 ledger and rulings

Run 38981994858 / job 117244738785 observed three real public Scene assertion failures for malformed kind/source/level and two passing empty/missing controls; the new producer-owner assertion also failed. Native input inspection in run 38982162444 / job 117245271522 proved rule_without_subjects for the future missing module, so that failure is not counted as a type comparison RED.

Ruling: isolate the fixed authored type intent from the whole-module guard in its native type fixture. The guard requires an actual existing source owner and gets a separate test; a missing owner must never be sold as an absence PASS. The authored type Target remains identical during source mutation tests. Also, string-Enum literal equality is accepted by TypeScript, so static controls corrupt the actual returned DTO field/return; raw comparison decisions are tested by the native PARTIAL witness instead.

Native site proof: run 38984148431 / job 117251581938 measured predecessor 865 and candidate 866 unresolved calls, with identical UNKNOWN-ID multisets. The one genuine added unresolved site was speculative AtlasDeviation.__post_init__ / object.__setattr__; the two other added/removed pairs were unchanged calls whose comprehension line identities shifted. Root approved removing this unnecessary normalizer: the new internal DTO has no legacy constructor, its actual producer already supplies the nominal Enum, and the actual JS decoder owns unknown wire ingress. Raw-control mutations now target the actual to_wire method. Its real new caller remains explicitly PARTIAL; no complete receiver proof is claimed.
