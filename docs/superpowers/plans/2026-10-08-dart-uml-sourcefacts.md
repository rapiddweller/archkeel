# Dart UML SourceFacts Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. A Luna implementer owns each task; a fresh Luna reviewer checks correctness and scope before the next task. The coordinating agent accepts the integrated result.

**Goal:** Implement [#347](https://github.com/rapiddweller/archkeel/issues/347): source-only Dart UML facts with explicit evidence and coverage, demonstrated by a realistic nested Dart application whose independently authored Target reaches from component responsibilities down to UML members and relationships.

**Architecture:** Preserve SourceCollector → SourceFacts → Core → shared graph/comparison/renderer. Keep Target independent of observation. Reuse existing TypeScript member receipts and source-record shapes where their semantics fit Dart.

**Tech Stack:** Python 3.11+, existing pytest/Make/browser tooling. The approved official Analyzer uses Dart >=3.9,<4 and exactly `analyzer: 10.2.0` with a committed lockfile.

**Spec:** Issue #347 and its owner comment; existing `docs/architecture/uml-model-target.md`, `docs/architecture/language-adapter-target.md`, AD-97 and AD-210. Baseline: `05c56a18786d5d0e97e9725b06a435a9ae72c5f1`.

## Owner decisions — 2026-10-08

- Backward compatibility is not required for this development-stage work. Replace the affected Dart profile, fixtures and installation path coherently; do not retain an import-only fallback, dual collectors or old payload acceptance solely for legacy users. Do not delete unrelated compatibility code.
- Expand the Dart demo beyond a flat UML sampler. Define meaningful smaller components and multiple nested levels, each with responsibilities.
- Author the demo Target before its source implementation: component boundaries and dependencies first, then modules, UML classifiers, members, signatures and required relationships. Never generate Target from As-Is.
- Demonstrate and verify the report at deeper scopes, not only the top-level screenshot.

## Approved runtime and execution

The user approved this plan and execution on 2026-10-08. Use the official Dart Analyzer as the single Dart collector through the existing process port, with a Dart SDK, explicit dependency setup and no installation during analysis. No legacy fallback. Luna implements and reviews the five tasks sequentially; the parent integrates and verifies.

## Demo design brief

Use a small order/checkout application in `fixtures/H-uml-dart`, without a web server, database or Flutter dependency. Set both the Dart package name and scan namespace to `commerce`; define matching source/module identities explicitly. The following boundaries are a proposed demo design, not facts inferred from current source:

```text
Demo root
├── presentation                 accept requests; map input to checkout
├── ordering                     own order state and checkout rules
│   ├── application              coordinate checkout and persistence
│   ├── ports                    declare persistence interfaces
│   └── domain                   own domain invariants
│       ├── orders               order, line items and lifecycle
│       └── pricing              totals and discount policies
└── adapters                     implement ports without owning domain policy
    ├── memory                   store orders in memory
    └── diagnostics              format a receipt or audit message
```

The required drilldown is `ordering → domain → orders → order.dart → Order → member`. Every component level must contain real responsibilities and source, with at least two siblings at the intermediate levels; no empty wrappers added merely to increase depth.

Define `Order`, `OrderLine`, `OrderStatus` and its literals; a pricing interface and concrete implementation/base; `CheckoutService`; an order repository interface and in-memory realization; and an input controller. Include private state, static helpers/constants, aliases, ordered/defaulted parameters, constructors and a recorded local binding. Each exists to serve the checkout flow or exercise a named report behavior.

Dependencies: presentation uses ordering's public application API; application uses domain and ports; adapters implement ports and may use domain values; domain does not depend on presentation or adapters. Within domain, pricing may use orders, not the reverse. A small composition entry point wires concrete implementations. Record its ownership explicitly.

Use existing recursive `inside` contracts for architectural containment and `declarations.uml` for lexical definitions. These are different parent relationships. Every component gets responsibilities, intended public surface, allowed dependencies and provenance. Every planned module/classifier/member gets ownership, responsibility and appropriate UML traits. Declare required static relationships independently of import permissions; do not claim runtime dispatch or composition from an interface alone.

Closed scopes are deliberate inventory requirements, not a decoration. Require complete classifier-member coverage where the collector can certify it. Keep genuinely unobservable module/call inventories open with an explicit reason; never manufacture PASS to make the demo look complete.

## Global Constraints

- KISS/SPOT: no second graph, renderer, policy engine or plugin framework.
- Collector facts contain no Target, contract decisions, ownership policy or layout.
- No legacy-only fallback, duplicate Dart path or migration layer. Invalid or unsupported inputs still require explicit rejection or UNKNOWN.
- Syntax recovery, missing dependencies, ambiguous bindings and unsupported semantics cannot certify complete inventories or PASS.
- Do not enable Python-only rules merely because Dart publishes symbols.
- No arbitrary project-code execution, implicit package installation or unrecorded external resolution inputs.
- Use existing Make workflows. Local verification precedes CI; merge/publication are outside this task.

## Review Focus

- Malformed whole units: `class Broken { ???` must not certify parsed syntax or complete members.
- Parts: retain library ownership and evidence locations; incomplete or conflicting part ownership remains UNKNOWN.
- Lexical shadowing: a local `helper` must not resolve to an unrelated top-level helper.
- Constructors, factories, mixins and extensions: unsupported distinctions remain explicit UNKNOWN rather than invented methods, inheritance or creation.
- Dependency resolution: missing inputs and absent capability receipts remain UNKNOWN. Removed wire/profile versions are rejected explicitly rather than silently reinterpreted.
- Nested scopes: a deep UNKNOWN or FAIL must retain its owner and evidence in the applicable scope and aggregate verdict; navigation/filtering cannot hide it.

## Task 1: Author the nested demo Target and acceptance map

**Files:** `fixtures/H-uml-dart/docs/target.md`, `pubspec.yaml`, `archkeel.toml`, its root `architecture-contract.json`, nested contracts under `fixtures/H-uml-dart/contracts/`; `tests/test_dart_uml_acceptance.py` for structural intent checks.

**Interfaces:** Existing recursive `inside` mounts, component IDs and `declarations.uml`; no new graph schema. Produces the independently authored Target used unchanged by Tasks 3–5.

- [x] Specify the checkout use case and the concrete responsibility/dependency tree above. Resolve composition-root ownership and concrete source/module identities before collecting As-Is.
- [x] Define all nested components, public surfaces and permissions; map planned modules to the correct physical scope and classifiers/members to lexical parents.
- [x] Declare UML types, exact signatures, visibility, static members, literals, aliases/constants and required source relationships for every demo leaf. Document scope completeness separately.
- [x] Add Target validation checks for three real component levels, responsibilities/provenance, mounted ownership, valid endpoints and member signatures. Cover a misowned child/endpoint negative through existing trust-boundary tests.
- [x] Record a compact acceptance table: user journey, intended scope, expected visible entities, PASS/FAIL/UNKNOWN variant and supporting artifact.
- [x] Fresh Luna review of the independent design before source implementation; no observed graph supplied as its oracle.

## Task 2: Integrate the single Dart inner-facts profile

**Files:** `src/archkeel/ir/facts.py`, `ir/profiles.py`, `ir/source_graph.py`, `analyzer/process.py`, `check/evaluation/evaluate.py`; relevant source-facts/observation schemas and focused protocol/profile tests.

**Interfaces:** Consume current `SourceFacts`, `Capabilities`, `MemberInventory`. Replace `archkeel-dart-directives` with `archkeel-dart-analyzer` for Dart requests with `imports`, `unknowns`, `symbols`, `calls`, `references`, `bindings` and the exact `inner-uml-v1` capability. Update current producers, consumers, fixtures and schema together. Keep one default profile per language; no multi-profile registry is needed for legacy support.

- [x] Add failing tests for current-profile protocol acceptance, invalid capability rejection, language mismatch, and explicit rejection of removed profile identities. Missing current evidence still remains UNKNOWN.
- [x] Extend the existing registration and assembly paths; validate source identity and member receipts at the existing trust boundary.
- [x] Permit explicit complete Dart enum/member receipts; keep module-level inventories partial unless separately proven. Calls present in a section do not prove exhaustive dispatch.
- [x] Run focused collection/profile/member-inventory/source-graph tests and `make lint typecheck`; stage for independent review. Commit the profile migration together with Task 3's producer so no commit leaves the default Dart collector incompatible with Core.
- [x] Fresh Luna task review: both specification compliance and correctness required.

## Task 3: Collect native declarations and whole-unit coverage

**Files:** `src/archkeel/analyzer/dart/native/pubspec.yaml`, `pubspec.lock`, `bin/collect.dart`, narrowly scoped native `lib/` source as needed; replace the existing Dart Python entry with a thin runtime launcher and explicit setup command; `tests/test_dart_inner_collect.py`; Make setup/check targets and package README.

**Interfaces:** One stdin request and stdout response using existing collection protocol 2.0.0 and Task 2's profile. Emit existing SourceFacts record shapes directly; adapter-local ASTs never cross the port. Include collector source/dependency identity and actual Dart runtime in provenance.

- [x] Add a failing native-process test for the independently specified H-uml-dart source from Task 1: classifiers, enum literals, fields, functions/methods, signatures, named/optional parameters, visibility, static members, aliases and constants retain source locations and identities.
- [x] Pin official Analyzer 10.2.0 and commit its lockfile. Ship the native package source in the existing wheel/sdist; ignore/exclude `.dart_tool` and local build products. Add `archkeel-dart-setup` and `make dart-setup` as explicit dependency preparation for the installed native package. During scans the existing Python entry launches native `dart` with the prepared absolute `--packages` and script paths, replacing itself rather than collecting/merging two results. Missing SDK/setup must fail clearly; no downloads or import-only success during scans.
- [x] Validate requests and selected paths. Parse complete units with the official AST; use direct declarations for inventory receipts, excluding inherited/synthetic members.
- [x] Add negative checks for malformed units, invalid parts, duplicate declarations and unsupported declaration kinds. Only certify complete inventories when every relevant declaration is represented.
- [x] Record and validate every non-SDK source/configuration input used for resolution. Keep paths outside the snapshot unavailable unless the existing port explicitly permits and records them.
- [x] Implement the independently authored demo source from Task 1 and validate it with the actual Dart compiler/analyzer; do not rewrite its Target to match output.
- [x] Run Dart format/analyze and focused real-process tests; review and commit together with Task 2's reviewed profile migration.
- [x] Fresh Luna task review before relationship implementation.

## Task 4: Publish resolved sites and explicit limits

**Files:** native collector source from Task 3 and `tests/test_dart_inner_collect.py`; only existing shared record validation where evidence requires it.

**Interfaces:** Existing base declarations, call/reference sites, candidate/evidence identities, result bindings and member receipts. The existing graph derives `inherits`, `realizes`, `calls`, `references`, `creates`, `instance_of` and bindings from these records.

- [x] Add failing assertions for pricing inheritance/realization, repository realization, controller/application and checkout/helper references/calls, and direct Order creation/result bindings using the independently authored demo source. A resolved interface method is not proof of the runtime implementation invoked.
- [x] Resolve only evidence-backed local/static sites. Retain candidates and explicit reasons at ambiguous/dynamic/external sites; never infer a relationship from a matching spelling alone.
- [x] Test local shadowing, import prefixes/show/hide, constructor/factory distinctions, mixins/extensions, missing packages and part ownership. Unsupported cases must lose proof, not silently disappear.
- [x] Run collector, graph and comparison tests plus Dart checks; review and commit.
- [x] Fresh Luna task review before demo acceptance.

## Task 5: Prove nested CLI, browser and packaging behavior

**Files:** `fixtures/demo_catalog_uml.py`, existing `fixtures/H-uml-dart/` source/Target documentation, new `tests/test_dart_uml_acceptance.py`, `tests/test_uml_demo.py`, `tools/report_browser.py`, `Makefile`; relevant reference/architecture docs and generated demo catalog.

**Interfaces:** Existing replay/ordinary CLI, shared As-Is/Target/Diff report and browser helper. Use the selected single Dart collector through the existing process configuration. Replace the old flat/import-only demo; small declaration microcases belong in focused tests.

- [x] Add `uml-dart-match` PASS, deep signature mismatch FAIL, certified missing-member FAIL, forbidden dependency FAIL and partial-resolution UNKNOWN variants. Their complete nested Target files are byte-identical across variants; only source changes. The missing member must be referenced only by Target so the source remains valid. The forbidden edge crosses a real nested component boundary.
- [x] Assert the exact failed aspect/subject, evidence locations, disjoint observed/Target IDs, and explicit UNKNOWN reasons. Assert evaluation receipts at root, intermediate and deepest scopes; deep uncertainty cannot become aggregate PASS. Valid syntax alone cannot prove a Target match.
- [x] Adapt `_open_uml_details` and `_check_inner_uml` to the authored nested demo route instead of hard-coded `demo/core` and the Dart branch expecting no observed UML. Reuse `tests/test_recursive_inside_independent_contracts.py` and the nested Target authentication test in `tests/test_target_graph.py`.
- [x] Verify the complete browser journey from root through all three component levels to module/class/member and back. At each level switch As-Is/Target/Diff and confirm scope, breadcrumbs/back navigation, selection, responsibilities and evidence ownership. Verify sibling/cross-boundary relationships, readable members, non-overlapping nodes and identical visible/hit paths. Confirm interaction does not mutate the report payload; capture overview, nested-component, UML/member, FAIL and UNKNOWN artifacts.
- [x] Extend `make demo-uml` and a focused native-Dart Make target. Fail the explicit native target if prerequisites are missing; do not report a skipped native test as acceptance.
- [x] Document the selected single installation path, demo component responsibilities, supported observations and remaining limits; add a concise architecture decision and catalog update.
- [x] Run focused acceptance, `make check`, `make demo-uml`, relevant real browser checks, `make self-observation`, `make against BASE=origin/main`, and build/smoke where packaging changed. Inspect actual verdicts and do not widen baselines to pass.
- [x] Fresh Luna whole-change review; resolve confirmed defects and record any remaining portability/CI-only gates. Do not merge or close #347 without all its acceptance evidence.

## Baseline evidence

`uv run --locked python -m pytest -q tests/test_dart_profile.py tests/test_dart_unknowns.py tests/test_uml_source_facts.py tests/test_collection_protocol.py`: **98 passed**, 5.55 s, on the unchanged base.

Three independent Luna research passes checked Core integration, native Analyzer feasibility and demo/browser acceptance. No implementation or new native behavior has been verified. CI was not run.

## Plan revision verification

The 2026-10-08 owner correction removes legacy preservation, the dual-collector proposal and its compatibility tests. It adds a Target-first demo design task, three genuine nested component levels, UML detail for every demo leaf and end-to-end deep report acceptance. This revision changes the plan only; the 98-test result above belongs to the unchanged baseline, not the proposed demo.

## Completion — 2026-10-08

Implemented locally on `feat/dart-uml-sourcefacts` with sequential Luna implementation/review, Superpowers and Ponytail. Native Dart replaces the directive-only collector; the independent nested Target and all five Dart demo variants are complete. Final implementation: `af13edc3`.

**LOCAL VERIFIED:** `make check` (6088 passed, 282 skipped), 648 report tests, six updated desktop/mobile browser cases, the complete catalog browser pass, 13 UML demo outcomes, exact `make against BASE=origin/main` amendment validation, and installed wheel/sdist smoke checks. All five Dart variants compile. D-self was regenerated; the unresolved-call baseline tightened 720 → 714. Existing own-architecture UNKNOWNs remain explicit.

**CI-ONLY VERIFICATION:** Linux/Windows and Dart 3.9.0/3.12.2 matrices were not run. No push, merge, release or issue closure.

Local acceptance record: `test-artifacts/dart-uml/verification.md`. Final reports, screenshots and browser traces: `test-artifacts/dart-uml/delivery-browser/`. Reviews and test logs are retained beside them.
