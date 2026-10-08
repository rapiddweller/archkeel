# Flutter Demo Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Luna implements and reviews each task. The parent accepts the integrated result.

**Goal:** Deliver a runnable representative Flutter demo, independent nested UML Target, and measured capability/limitation evidence from real GitHub source.

**Architecture:** Extend the existing fixture/catalog/report workflow with `fixtures/I-flutter-shop`. Keep G/H as focused controls. Reuse the native collector and shared graph; never generate intent from observation.

**Tech Stack:** Existing Python/pytest/Playwright/Make; Flutter SDK and flutter_test only for the app; native collector remains pinned as already approved.

**Spec:** `docs/superpowers/specs/2026-10-08-flutter-demo-design.md`. User requested this continuation after approving the original Dart UML implementation and Luna execution. Baseline `d8e81a587f0cec4eabc6e34e758b03c8ea73d2de`.

## Global Constraints

- Work on branch `feat/dart-uml-sourcefacts` in the repository checkout.
- Demo package/namespace `shop`; fixture `fixtures/I-flutter-shop`; source root `lib`.
- Target authored before source; no Target from As-Is; unchanged Target bytes across source variants.
- Agent-authored permissions stay `decided_by: agent`. Required external Flutter inheritance remains in Target even when UNKNOWN.
- No legacy fallback, new renderer/schema, scan-time dependency installation or unrecorded resolution inputs.
- Original source only; no copied AGPL implementation. Runtime demo uses Flutter SDK/flutter_test, no third-party app framework.
- Use existing Make workflows, shortest coherent code, exact evidence; no push/merge/CI/publication.
- Direct Dart SDK `/opt/homebrew/share/flutter/bin/cache/dart-sdk/bin/dart`; Flutter `/opt/homebrew/share/flutter/bin/flutter`; `DART_SUPPRESS_ANALYTICS=true`.

## Review Focus

- Missing external Flutter types cannot prove inheritance or dispatch; expected required relationship UNKNOWN.
- Duplicate submit, async completion after disposal and stream cancellation must not corrupt order state or cause widget errors.
- Offline cached reads must be labelled; failed checkout retains the cart for retry.
- Nested Target intent must survive source mutation, and root verdict cannot hide deep FAIL/UNKNOWN.
- Reference unsupported syntax/codegen remains in the measured source scope, never excluded to manufacture PASS.

## Task 1: Independent Target and structural acceptance

**Files:** `fixtures/I-flutter-shop/{README.md,pubspec.yaml,archkeel.toml,architecture-contract.json,contracts/*.json,docs/target.md}`; `tests/test_flutter_demo.py`.

**Interfaces:** Produce the complete proposed source/module/class/member/signature inventory in Target JSON and a compact source-layout table in `docs/target.md`. Task 3 implements those names/signatures. No `lib` source yet.

- [x] Write a failing target-validation test for responsibilities/provenance, ownership, three meaningful component levels and required UML inventory/relationships.
- [x] Author the fixture Target for the spec's journey/boundaries. Decide exact names/signatures once in the Target. Plan generic state, enhanced enum, nullable/Future/Stream signatures, factory vs generative construction, Flutter view/state lifecycle and constructor injection where they serve the journey.
- [x] Include an external Flutter referenced endpoint and required inheritance relationship. Do not invent unsupported graph kinds/traits; document their absence.
- [x] Validate the contract tree and target graph without observing nonexistent source; verify permissions are closed and module/member ownership is coherent. Record intended source-only variants and expected aspects rather than guessing whole-report PASS.
- [x] Run focused structural tests, review the diff and commit. Fresh task review before source implementation.

## Task 2: Correct generic Analyzer element identity

**Files:** `src/archkeel/analyzer/dart/native/lib/collector.dart`, `tests/test_dart_inner_collect.py`; existing Dart architecture decision/known-limits notes if needed.

**Interfaces:** Native SourceFacts and existing shared graph only. The generic factory and inherited-method regressions live in `tests/test_dart_inner_collect.py` (`test_native_generic_redirected_factory_stays_unknown_in_core_graph`, `test_native_generic_inherited_call_resolves_in_core_graph`).

- [x] Add RED regressions: generic redirected factory construction must remain partial/UNKNOWN; inherited generic local calls must resolve to the selected base declaration, as non-generic controls already do. Verify through strict facts and Core creates/calls comparisons, not message strings.
- [x] Inspect official Analyzer element API and use canonical declaration identity for instantiated members at the shared lookup boundary. Do not special-case class names, strip generic strings, or treat factories as generative. External targets remain unresolved.
- [x] Run focused regression tests, native Dart format/analyze, and relevant existing constructor/inheritance/provenance tests. Review the diff and commit; fresh review before the app task.

## Task 3: Runnable Flutter flow

**Files:** `fixtures/I-flutter-shop/lib/**/*.dart`, `test/*.dart`, minimal `web/index.html`, `pubspec.lock`, `.gitignore`, `analysis_options.yaml` only if needed; Makefile and fixture README.

**Interfaces:** Implement Task 1's inventory, with the Target immutable unless a documented design defect is reviewed. App entry `lib/main.dart`; Flutter tests drive real widgets and async state, not a Python mock.

- [x] Write and run focused failing behavior tests for catalog→cart→checkout→order detail, offline/error retry preserving the cart, duplicate submit protection and disposal/stream cleanup.
- [x] Implement the spec using platform widgets/state/navigation and deterministic services. Avoid generic command buses, fake product abstractions, timing-dependent tests and unneeded dependencies.
- [x] Add `make flutter-demo-check` to orchestrate explicit `flutter pub get`, format check, analyze, tests and web build; capture exact SDK versions and test output. Keep analysis itself installation-free.
- [x] Verify actual Flutter behavior and build; review/correct only source code, not Target to match observed facts. Commit; fresh task review.

## Task 4: ArchKeel integration, mutations, browser and limitations

**Files:** `fixtures/demo_catalog_flutter.py`, `fixtures/architecture_demo.py`, `tests/test_flutter_demo.py`, `tools/report_browser.py`, Makefile as needed, fixture README and `docs/architecture-demo.md`; focused native collector tests only for confirmed gaps.

**Interfaces:** Reuse Variant, replay, existing report parser/comparison and browser helpers. Source-only cases `flutter-shop`, `flutter-signature-fail`, `flutter-missing-member-fail`, `flutter-forbidden-dependency-fail`, `flutter-dynamic-unknown`, `flutter-unsupported-declaration`.

- [x] Write failing end-to-end assertions for target byte identity, exact signature/member/dependency findings, local PASS evidence, required external/dynamic relationship UNKNOWN and unsupported-declaration gaps. Assert actual report and coverage semantics rather than assuming exit codes.
- [x] Add six catalog cases and shared replay integration without special collector behavior. Expose generated demo guide entries. Keep expensive new browser checks focused on this fixture.
- [x] Exercise desktop/mobile deep navigation in all three views, evidence, sibling/cross-boundary relationships, FAIL/UNKNOWN detail and stable payload. Save screenshots/reports locally.
- [x] Run the unchanged pinned Compass source snapshot with the ordinary native collector; record manifest/digests, selected source scope, diagnostics and unresolved calls. Use no network or external package sources during the scan.
- [x] Record a concise evidence-backed matrix against Compass, TodoMVC and Ente: demonstrated, syntax-only, UNKNOWN/rejected, unmodeled, feasible follow-up. Fix confirmed correctness defects in the smallest shared place with a regression; larger capability extensions remain explicit proposals.
- [x] Run focused Flutter/Dart/catalog/browser tests, `make lint typecheck`, `make check`, `make demo-uml`, `make against BASE=origin/main`; build/smoke only if packaging changed. Preserve existing baseline ceilings and explicit UNKNOWNs.
- [x] Fresh whole-change review, parent integration acceptance and updated completion evidence. Keep commits local.

## Completion

Accepted locally at product commit `19052fdb6dceb88dd355de0c23765d9366a5d0a5`. Fresh `make check`: 6,101 passed, 283 skipped; full browser gate: 649 passed plus generated-report acceptance. UML demo and package smoke passed. Flutter runtime, self-observation and against receipts are recorded with their exact revisions in `test-artifacts/flutter-demo/verification.md`. Independent Luna reviews passed; remaining semantic and mobile-runtime limits stay explicit. No CI, push or merge.
