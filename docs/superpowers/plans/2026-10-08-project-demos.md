# Full-project Python, TypeScript and Flutter architecture demos

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` after the start gate. The user has authorized commit, push and merge after clean final-head CI; no additional approval gate is needed.

**Goal:** Publish one complete pinned Python, TypeScript and Flutter project, each with an independently authored nested Target, meaningful As-Is/Target/Diff, source-only FAIL and UNKNOWN examples, and deep desktop/mobile navigation.

**Architecture:** Preserve each source snapshot and provenance separately from the Target. Use the existing language collectors, shared graph/UML contract, report generator, browser tests and gallery path. Repair only measured source-fact gaps at their shared owner; keep baseline and mutation uncertainties explicit.

**Tech Stack:** ArchKeel Python/pytest/uv; Dart Analyzer native collector; TypeScript Tree-sitter collector/config resolver; shared JSON graph/contract; existing HTML/JavaScript reports and browser acceptance.

**Spec:** [`../specs/2026-10-08-project-demos-design.md`](../specs/2026-10-08-project-demos-design.md). This plan is contingent on PR #414 passing its PR gate and merging.

## Global constraints

- The demo branch starts from PR #414's merged head after its required PR checks are green. Track Main CI separately: its final outcome is required before overall handoff, but a long-running Main job does not block starting demos after PR verification.
- Compass analysis includes all 111 pinned `app/lib/*.dart` inputs representing 89 logical libraries. Keep all 22 generated `part` files; attribute each to its parent library. `pubspec.yaml` is configuration/provenance, not a Dart module.
- Python analysis includes all 72 pinned `app/*.py` files. Preserve all 79 files under `app/` (72 Python, five SQL, one stub and one migration template); preserve the full 125-entry upstream tree manifest, but do not vendor unrelated repository tests or the full tree. Keep needed root README, license and configuration.
- Nest/Mikro keeps all 45 original `src` files byte-identical (42 `.ts`, two config templates, one ORM snapshot). Upstream `tsconfig.build.json` selects 39 runtime TypeScript files and excludes three specs. README-required byte copies of the two config templates create two additional prepared inputs: 41 build inputs. Keep original hashes and derived-file lineage separate.
- Do not install dependencies, fetch during analysis, or execute upstream application/test code. Keep resolver inputs explicit and pinned. Only run ArchKeel collection, tests, report generation and browser acceptance.
- Author each Target from pinned docs and source declarations before collecting its acceptance report. Never derive ownership or UML from observed SourceFacts. Record its digest before collection; all source-only variants keep those exact Target bytes.
- Each project has separate source-only examples for (1) a forbidden architecture edge, (2) a deep UML member/signature mismatch, and (3) a relationship that changes from proven to UNKNOWN when its receiver/call becomes dynamic. Record exact source evidence and expected assessment.
- Require a non-null UML comparison for each unchanged project with the full selected input inventory present. Full file inventory is distinct from complete semantic evidence: a bounded source-coverage FAIL may coexist with a comparison over authenticated, validated partial observations. Preserve Core coverage FAIL, diagnostics and exit code 2; missing/unsupported evidence remains UNKNOWN, observed contradictions may FAIL, and an incomplete comparison must never receive aggregate PASS. Missing selected inputs, invalid contracts/protocols and untrusted facts remain blocked. Do not weaken `complete_requires`.
- Keep all upstream bytes, license notices, immutable source URLs and hashes. Never alter vendor headers to satisfy repository hygiene; add only narrow, path-and-hash-bound header exceptions.
- No compatibility aliases, generic fixture framework, dependency installation, parallel renderer or source-file-count padding. Keep `I-flutter-shop` as the smaller runnable control.

- Mutations are temporary overlays/copies; vendored originals stay byte-identical and each variant changes only its intended source paths.

## Review focus

- **Dart inherited `super.key` without SDK inputs:** preserve the source parameter; if Analyzer cannot resolve its inherited type, record `signature_complete=false` and compare it as UNKNOWN. Do not infer `dynamic` from failed resolution; an explicitly source-declared `dynamic` remains a known annotation. Do not infer an implicit `null` default from omitted child syntax when a resolved parent parameter has a non-null default; use that Analyzer fact only when trustworthy, otherwise keep it UNKNOWN. Add a `Parent({String key = 'x'})` / `Child({super.key})` regression. Do not label absent type knowledge as a syntax gap. Task 2.
- **Dart local/accessor identity:** local identities include lexical function-expression scope; getter/setter preserve both source operations without first-match element misbinding or lossy merging. Real ambiguous duplicates stay gaps. Task 2.
- **Dart generated parts:** all 111 physical inputs map to exactly 89 library owners; generated parts are not independent Target modules. Tasks 1 and 6.
- **Partial UML under source-coverage failure:** design and test one shared Core boundary before project proofs. Only authenticated, validated partial observations are eligible; coverage status and diagnostics remain unchanged. Do not whitelist diagnostic strings, create a second graph/receipt, or let incomplete evidence produce aggregate PASS. Task 4.
- **Python non-Python boundaries:** SQL, `.pyi` and `.mako` remain preserved provenance, not Python facts. Task 8.
- **Nest decorators/packages:** do not infer framework route/DI/ORM execution from dropped decorators or resolve ambient package installs. The UNKNOWN example must make a required invocation (`calls` or `creates`) dynamic and prove the same relationship assessment changed. Task 11.

## Pinned project preflight

| Project / pin | Selected source and connected feature | Known status and limits |
|---|---|---|
| Flutter Compass, [`flutter/samples@5541c59ab8e9d7e74c1a35ef22bd43a487fc596c`](https://github.com/flutter/samples/tree/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/compass_app/app/lib) | 111 Dart inputs → 89 libraries; 22 generated parts in 11 model libraries. Auth/session → search/config → results → activity selection → booking create/detail/share → home list. | Snapshot digest `c6c1b8fe62fbc950af3b3dc4a033cac300bdeec2564e563909504a69df753e72`. Existing probe has 45 source gaps and null comparison; 492/1,526 calls resolved. See `compass-full-target-feasibility.md` and `compass-target-intent.md` in the research receipts. |
| Python RealWorld, [`nsidnev/fastapi-realworld-example-app@029eb7781c60d5f563ee8990a0cbfb79b244538c`](https://github.com/nsidnev/fastapi-realworld-example-app/commit/029eb7781c60d5f563ee8990a0cbfb79b244538c) | 72 Python files under `app/`. Register/login/JWT → profiles/following → articles/feed/favorites → comments/tags → async repository/SQL boundary. | MIT, archived 2022; use only as a frozen architecture reference. Full tree has 125 tracked entries; vendor the 79 `app/` files and needed root docs/config, not unrelated tests. No ArchKeel comparison has been measured. See `python-project-demo-research.md`. |
| Nest/Mikro RealWorld, [`mikro-orm/nestjs-realworld-example-app@a6818d84b6a019cf2df4ef391dc87cea7d02c6a9`](https://github.com/mikro-orm/nestjs-realworld-example-app/commit/a6818d84b6a019cf2df4ef391dc87cea7d02c6a9) | 45 original `src` files, 42 `.ts`; 39 upstream build `.ts` files plus two README-derived config copies = 41 prepared inputs. Auth → articles/feed/comments/favorites/profiles/follow/tags → services/entities/migrations. | MIT. Current Tree-sitter profile drops decorator metadata; package exports/resolution and a non-null comparison remain feasibility questions. Do not claim route/DI/ORM runtime semantics. See `typescript-project-demo-research.md` and the pinned snapshot.

**Execution ruling:** Reuse the three existing live Luna agents for bounded implementation/review tasks, one product writer at a time. Fresh spawn failed at the thread limit; record this harness constraint and do not request more capacity or approval.

## Shared interfaces and paths

| Concern | Existing/new owner | Contract |
|---|---|---|
| Pinned inputs | `fixtures/J-compass/SNAPSHOT.json`, `fixtures/K-python-realworld/SNAPSHOT.json`, `fixtures/L-nest-realworld/SNAPSHOT.json`; `tests/test_project_demo_snapshots.py` | Upstream commit, path, byte hash, source URL and selected/excluded reason; Compass parent-library mapping; Nest template-to-derived mapping. |
| Targets | Each fixture's `architecture-contract.json`, `contracts/*.json`, `docs/target.md`, `README.md`, `archkeel.toml` | High-level responsibility → nested component → owned logical module → principal classifier/member/relationship contracts and allowed edges. Target hash frozen before that project's first collection. |
| Dart identity/signatures | `src/archkeel/analyzer/dart/native/lib/collector.dart`; focused `tests/test_dart_*.py`, `tests/test_uml_comparison.py` | Full syntax inventory with honest signature completeness, lexical local identity and distinct getter/setter operation identities. |
| Shared mixin UML | `src/archkeel/ir/{architecture_graph,source_graph,graph_codec,facts_validation}.py`; `schema/{architecture-graph,architecture-ir-common,architecture-ir-decoded,source-facts}.schema.json`; `tools/architecture_graph_schema.py` | First-class mixin classifier plus distinct class `with` relationship; shared codec, validation and evaluator vocabulary. No old-vocabulary compatibility mapping. |
| Comparison/report | `src/archkeel/check/{uml,uml_compare,uml_evaluation}.py`, `src/archkeel/check/evaluation/evaluate.py`, `src/archkeel/check/observe.py`, `src/archkeel/ir/report_graph.py`; `src/archkeel/render/assets/flow.js` | One Core UML receipt over validated observations, including an eligible partial observation; coverage failure/diagnostics stay truthful and incomplete evidence cannot produce aggregate PASS. Same graph, Target and comparison data across report views. |
| Catalog/gallery | `fixtures/demo_catalog_{compass,python_realworld,nest_realworld}.py`; `fixtures/architecture_demo.py`; `tools/{report_pages,report_browser}.py`; `tests/{test_report_pages,test_report_browser}.py` | Canonical project reports appear before per-project regression variants; small teaching fixtures stay a separate labeled section. |

## Dependency-ordered tasks

### Task 0: CI gate

**Files:** none.

- [ ] Verify all applicable PR #414 jobs are green on the exact pushed head, including Windows native and required checks; confirm merge and record the merge SHA.
- [ ] Start the demo branch from that merge. Track Main CI as separate evidence and require its final result before final handoff, not before demo work begins.

### Task 1: Preserve selected source snapshots and provenance

**Files:**
- Create `fixtures/J-compass/lib/**`, root `pubspec.yaml`, `LICENSE`, `SNAPSHOT.json`; retain original `compass_app/app/...` source paths in provenance. Keep Dart files and pubspec at the collector root so `package:` imports and native snapshot discovery work without a wrapper layer.
- Create `fixtures/K-python-realworld/app/**` (all 79 app files), `LICENSE`, `README.rst`, `pyproject.toml`, `setup.cfg`, `poetry.lock`, `alembic.ini`, `SNAPSHOT.json` with the 125-entry tree manifest.
- Create `fixtures/L-nest-realworld/src/**` (all 45 originals plus two derived config copies), `LICENSE`, `UPSTREAM_README.md`, `package.json`, `yarn.lock`, `tsconfig.json`, `tsconfig.build.json`, `SNAPSHOT.json`. Preserve the pinned README under `UPSTREAM_README.md`; later Target authorship owns fixture `README.md`.
- Modify `tests/test_repository_hygiene.py`; create `tests/test_project_demo_snapshots.py`.

**Interfaces:** outputs immutable source path/hash/URL lists. Keep original and derived Nest inputs distinguishable; keep full Python tree provenance while only vendoring the selected app.

- [ ] Add tests asserting Compass 111 input files map to 89 libraries and 22 parent-owned generated parts.
- [ ] Add tests asserting Python has all 79 `app/` files, exactly 72 selected `.py` files, plus the unvendored tree-manifest count of 125; do not vendor upstream tests.
- [ ] Preserve/hash all 45 Nest `src` originals; verify upstream build scope 39 and three excluded specs. Copy `config.ts.example` → `config.ts` and `mikro-orm.config.ts.example` → `mikro-orm.config.ts` byte-for-byte; record source/destination hashes and mark these as derived, producing 41 prepared build inputs.
- [ ] Add a narrow repository-hygiene exception keyed by each exact vendored upstream Python path and pinned byte hash; assert every non-exempt Python file retains the ArchKeel header and no upstream file was edited.
- [ ] Fix the existing absolute-root-path guard at its shared boundary check, without blanket exemptions: a nested relative home-screen import must pass, while quoted absolute POSIX and Windows paths (including home-directory paths) remain detected. Keep this regression separate from the Python upstream-header exception.
- [ ] Run only snapshot/provenance/hygiene tests; no collector, package manager or upstream project execution. Commit snapshots and receipts.

### Task 2: Fix Dart lexical identity and honest signatures

**Files:** modify `src/archkeel/analyzer/dart/native/lib/collector.dart`; test `tests/test_dart_inner_collect.py`, `tests/test_dart_profile.py`, `tests/test_dart_unknowns.py`, `tests/test_dart_uml_acceptance.py`, `tests/test_uml_comparison.py`.

**Interface:** preserve existing SourceFacts schema; emit source-faithful declaration/member identity and signature completeness.

- [ ] Add RED tests for same-named locals in separate function-expression scopes; getter/setter member records sharing a Dart property name; true duplicate declarations; resolved and missing/invalid `super.key` element types; and a non-null comparison with an UNKNOWN incomplete signature. Include `Parent({String key = 'x'})` and `Child({super.key})` to verify the inherited default is read from a trustworthy resolved parent parameter or remains UNKNOWN.
- [ ] Verify failures at the focused collector and Core paths. For unresolved inherited parameters, preserve the parameter fact with `signature_complete=false`; do not guess `dynamic` or an Analyzer error type from failed resolution. An explicitly source-declared `dynamic` remains known. For local identity, keep function-expression scopes distinct. For accessors, preserve both operations and resolve each from its actual declaration, without lossy merging.
- [ ] Fix the smallest shared collector/indexing cause and run focused tests plus existing constructor/inheritance/provenance checks. Commit and independently review before Compass Target validation.

### Task 3: Add shared Dart mixin and `with` semantics

**Files:** modify `src/archkeel/analyzer/dart/native/lib/collector.dart`, `src/archkeel/ir/{architecture_graph,source_graph,graph_codec,facts_validation}.py`, `src/archkeel/check/{uml,uml_compare,uml_evaluation}.py`, relevant `schema/*.json`; tests `tests/test_dart_profile.py`, `tests/test_dart_uml_acceptance.py`, `tests/test_uml_classifier_facts.py`, `tests/test_uml_comparison.py`, `tests/test_uml_rendering.py`, `tests/test_schema_drift.py`.

**Interface:** shared graph recognizes a mixin declaration and a distinct `with` relationship; every producer/consumer uses the same serialized contract.

- [ ] Add RED Dart→Core→UML tests for a declared mixin, multiple `with` compositions and generated Freezed parts. Assert it is not classified as class inheritance.
- [ ] Implement the shared classifier/relationship vocabulary and its schema, codec, validation and evaluator handling. Do not add a Dart-only branch or compatibility alias.
- [ ] Run focused multi-language schema/graph tests and `make architecture-graph-schema`; commit and independently review before Compass Target validation.

### Task 4: Preserve shared UML comparison on eligible partial observations

**Files:** trace and modify only the shared owners in `src/archkeel/check/{observe.py,uml.py,uml_evaluation.py,evaluation/evaluate.py}` and `src/archkeel/ir/{facts.py,report_graph.py}` as needed. Add one structured source-resolution gap kind at explicit resolution sites in `src/archkeel/analyzer/typescript/collect.py`. Extend focused TypeScript collector, UML evaluation/comparison and report tests.

**Interface:** preserve Core coverage FAIL, diagnostics and exit code 2. Use the existing comparator and ordinary UML receipt for authenticated, validated partial observations. No diagnostic-text allowlist, serialized eligibility protocol, alternate graph or second receipt.

**Design review:** `task-4-implementation-map.md` records the traced boundaries and independent challenge. Its final rulings supersede the earlier proposal: no synthetic full-app closed TargetScope is required; partial aggregate PASS is withheld, never rewritten.

- [ ] Trace collection, fact validation, canonical Observation, runtime/rule/git/nested coverage, Target authentication, comparison and saved-report callers. Use a small typed in-memory eligibility state, blocked by default for custom results. Mint source eligibility only after validation, with nonempty exact selected physical inventory, every selected file read/parsed, rule coverage PASS, valid runtime, and Core failures exactly equal to the validated source-resolution gaps. Revoke on mixed blockers and every failed Target authentication path.
- [ ] Emit a shared structured source-resolution gap kind only at computed/nonliteral/unproven import and unresolved import/runtime-target resolution producers. Generic syntax/config/read/identity gaps stay blocked. Full parsed counts alone are insufficient: TypeScript syntax recovery currently increments them before reporting its gap. Do not infer eligibility from diagnostic titles, remedies or messages.
- [ ] Run the ordinary comparator after root/nested Target authentication. Preserve real FAIL and UNKNOWN assessments. Every emitted partial receipt has `assessment_complete=false`, including FAIL with no UNKNOWN assessment. If the ordinary comparison aggregates PASS, withhold its receipt; do not falsify the verdict or invent an UNKNOWN assessment. Authored principal API scopes remain normal Target intent; ownership tests separately prove full module ownership.
- [ ] Add a real TypeScript computed-import regression with full selected inventory, a proven signature contradiction (FAIL), and an absent required entity (UNKNOWN). Assert retained Core coverage FAIL/diagnostics/exit 2 and the same non-null standard receipt in live and saved reports, without reevaluation. Cover no-closed-scope FAIL, absent-entity UNKNOWN, and all-PASS receipt suppression.
- [ ] Add negative controls for malformed facts/protocol/evidence, collection failure, invalid Target/digest/nested contract, mixed runtime/rule/git blockers, missing selected inputs and a syntax gap despite full parsed counts. All remain blocked. Do not weaken `complete_requires` or turn missing evidence into proven absence.
- [ ] Run focused producer/Core/report tests and obtain independent spec and quality review before any full-project acceptance collection.

### Task 5: Author the Compass Target (no collection)

**Files:** create `fixtures/J-compass/{archkeel.toml,architecture-contract.json,docs/target.md,README.md}` and `fixtures/J-compass/contracts/{application,presentation,domain,data,utilities}.json`; create `tests/test_compass_project_target.py`.

**Interfaces:** consumes only Task 1 pinned source/docs and the source-based `compass-target-intent.md` research receipt. Produces the 89-library responsibility map and Target hash.

- [ ] Define application composition/environment, auth/session, routing, home/search/results/activities/booking presentation, domain, repository/service data and utilities as nested responsibilities with allowed dependency directions.
- [ ] Map each of 89 logical libraries exactly once; map each of 22 generated parts to its parent model library. Close principal member APIs for auth, itinerary/search, activity selection, booking create/detail/share, home booking list, repository ports, API/local services, model/serialization and generic `Command`/`Result` contracts.
- [ ] Test full ownership, non-empty nested responsibilities, declared UML/member signatures and Target validity from schema only. Do not run collection. Record Target digest; commit and review before Task 6.

### Task 6: Prove Compass full-source Target and variants

**Files:** create `fixtures/demo_catalog_compass.py`, `tests/test_compass_project_demo.py`; use `fixtures/J-compass/**`, existing collector/Core/report/browser paths.

**Interface:** consumes Task 2/3 collector and comparison behavior from Task 4 plus the frozen Task 5 Target. Produces full 111-input base inventory plus three source-only mutations.

**Measured prerequisite (Task 6a):** the first full-source probe found 30 unresolved Flutter `super.key` parameters classified as generic unsupported syntax. In the native Dart `_params` producer, use the existing typed source-resolution gap only when Analyzer evidence proves unavailable superclass binding. Null inherited-parameter binding or `InvalidType` alone is insufficient; invalid parameters on a resolved parent remain blocking. Preserve incomplete signatures, unknown types/defaults, source coverage FAIL and exit 2. Add native positive/negative and normal Core partial-receipt tests; no Core gate expansion. Review this separate fix before the full-project proof. Nine independent parent-scope Target errors were corrected from source and refrozen in Task 5; do not admit such errors as source resolution.

- [ ] Add tests for full input/library scope and non-null comparison; forbidden internal edge → architecture FAIL; deep required member/signature change → UML FAIL; a formerly proven required call made dynamic → relationship UNKNOWN.
- [ ] Collect all 111 files. Require the complete selected input inventory and `comparison != null`; preserve any source-coverage FAIL/diagnostics and allow only evidence-backed UNKNOWNs such as missing SDK/external call types. A partial comparison does not claim semantic completeness.
- [ ] For each variant, assert unchanged selected path set and Target digest, exact changed source anchor and expected rule/relationship assessment. The UNKNOWN test must compare the same target obligation before/after and prove the new dynamic call changes its result to UNKNOWN.
- [ ] Navigate As-Is, Target and actual Diff through responsibility, nested feature, logical library, class/member and source evidence. Record source/collector/Target digests and residual UNKNOWNs; commit and review.

### Task 7: Author the Python RealWorld Target (no collection)

**Files:** create `fixtures/K-python-realworld/{archkeel.toml,architecture-contract.json,docs/target.md,README.md}` and `fixtures/K-python-realworld/contracts/{runtime,identity,publishing,persistence}.json`; create `tests/test_python_realworld_project_target.py`.

**Interfaces:** consumes Task 1's 72 Python app files, 79-file app provenance and pinned RealWorld documentation. Produces an independent responsibility/library/UML map and Target hash.

**Measured prerequisite:** the pinned project declares `[tool.poetry.dependencies].python = "^3.9"`; the current reader only accepts `[project].requires-python`. Repair this at `src/archkeel/analyzer/runtime.py` and `src/archkeel/check/runtime.py`, with focused `tests/test_runtime.py` coverage, before authoring the Target. Preserve the upstream `pyproject.toml` bytes.

- [ ] Keep a present project requirement authoritative, including invalid values; use Poetry only when that key is absent. Reuse `packaging` for PEP 440 ranges and normalize supported positive-major numeric caret ranges (`^3.9` means `>=3.9,<4.0`). Unsupported forms stay blocking under the existing runtime state with truthful generic invalid-or-unsupported metadata diagnostics. No new protocol field, compatibility machinery, package manager or dependency. Test precedence, boundary versions and unsupported/invalid forms; keep runtime failures ineligible for partial UML.

- [ ] Map runtime/composition/API, auth/JWT, profile/following, article/feed/favorite/comment/tag, services/repositories and persistence responsibilities to every app module.
- [ ] Close principal source class/member contracts for one request journey from route/dependency through service to repository. Explicitly state SQL/template/stub and external database behavior not measured by Python facts.
- [ ] Test path ownership and Target schema without collection; freeze Target digest. Commit and review before Task 8.

### Task 8: Prove Python full app Target and variants

**Files:** create `fixtures/demo_catalog_python_realworld.py`, `tests/test_python_realworld_project_demo.py`; use `fixtures/K-python-realworld/**` and existing Python collection/report paths.

**Interface:** consumes the frozen Task 7 Target; produces full 72-file Python base plus source-only architecture FAIL, deep UML FAIL and UNKNOWN.

- [ ] Test complete selected Python module set and non-null comparison. Preserve truthful source-coverage status if bounded gaps remain. Add one forbidden internal dependency mutation, one required nested member/signature mismatch, and one required call changed from typed/resolved to dynamic so its relationship becomes UNKNOWN.
- [ ] Verify every mutation preserves path selection, pinned upstream input hashes other than the changed overlay, Target bytes and exact assessment evidence. Keep SQL/data-flow and external library semantics unknown.
- [ ] Record measured completeness, comparison/assessment counts, source hashes and reasons; do not run archived app/tests or install its dependencies. Commit and review.

### Task 9: Verify Nest/Mikro source-resolution feasibility

**Files:** inspect the pinned `fixtures/L-nest-realworld/{package.json,yarn.lock,tsconfig.json,tsconfig.build.json,src/**}` inputs and the existing TypeScript resolver/profile tests; change only a measured shared resolver defect and its focused tests if the pinned project demonstrates one.

**Interface:** consumes Task 1's immutable snapshot and 41 prepared build inputs. Produces a reproducible resolution report and a bounded decision on whether the existing Tree-sitter profile can preserve internal project facts without ambient packages or weakening source scope.

- [ ] Inspect exact pinned package exports, TypeScript settings and source imports, including the README-derived config copies. Do not install packages or inspect ambient `node_modules`; explicitly captured resolver inputs are permitted inside isolated snapshots.
- [ ] Reproduce the NodeNext export behavior with the existing resolver. Confirm whether the blanket export rejection affects this fixture and identify the smallest supported resolution shape, if any.
- [ ] Record resolved/unresolved internal imports and remaining syntax limits. Preserve unsupported external/decorator facts as UNKNOWN. Do not change upstream inputs, add compatibility aliases, or lower required scope.
- [ ] If a shared resolver defect is proven, add a focused failing test first, apply the smallest fix and independently review it. Preserve the copied `import(id)` behavior and its coverage gap; do not force a dynamic import to a static target. Otherwise record the limitation without claiming comparison feasibility; Task 11 must demonstrate a non-null comparison on the complete input inventory.

### Task 10: Author the Nest/Mikro Target (no collection)

**Files:** create `fixtures/L-nest-realworld/{archkeel.toml,architecture-contract.json,docs/target.md,README.md}` and `fixtures/L-nest-realworld/contracts/{runtime,identity,publishing,persistence}.json`; create `tests/test_nest_realworld_project_target.py`.

**Interfaces:** consumes pinned source/docs plus 41 prepared build inputs from Task 1; owns the two derived config files as composition/config modules and leaves three excluded specs outside runtime ownership.

- [ ] Define module/controller/service/entity/DTO/auth/persistence responsibilities and assign every one of the 41 prepared build modules exactly once.
- [ ] Close principal method/member contracts for auth, article/feed/favorite/comment/profile/follow/tag and persistence. State that decorator-based route/DI/ORM runtime edges are claimed only if source facts actually support them.
- [ ] Declare the source-backed `UserService.create` → `User` construction obligation before collection; Task 11 will make that invocation dynamic against the same Target. Property-method receiver dispatch remains an explicit profile limitation.
- [ ] Test ownership and Target validity without collection. Record Target hash and commit/review before Task 11.

### Task 11: Prove Nest/Mikro full build Target and variants

**Files:** create `fixtures/demo_catalog_nest_realworld.py`, `tests/test_nest_realworld_project_demo.py`; use `fixtures/L-nest-realworld/**` and existing TypeScript profile/report paths.

**Interface:** consumes Task 1's untouched 45-file upstream manifest, 41 prepared build inputs and frozen Task 10 Target. Produces non-null base and three source-only mutations.

- [ ] First verify the 45 original files remain byte-identical, the two derived config copies match their templates and the upstream 39 runtime files are all present. Resolve using only explicitly recorded config/package-metadata inputs; never inspect ambient `node_modules`.
- [ ] Add tests for non-null comparison with all 41 prepared inputs and truthful coverage FAIL if a bounded source gap remains; forbidden internal dependency → architecture FAIL; nested required member/signature mismatch → UML FAIL; and a previously proven required invocation (`calls` or `creates`) made dynamic → UNKNOWN. Use the source-backed `new User(...)` → `new (User as any)(...)` construction in `UserService.create`, retaining the exact Target `creates` obligation. The UNKNOWN assertion must show that same relationship assessment transition; merely missing decorators/packages does not satisfy it.
- [ ] Inspect exact pinned package manifests/lock entries for any supported export shape. Fix only a measured shared TypeScript profile defect necessary to preserve internal source facts or comparison. Do not infer Nest decorators or package execution; keep unsupported behavior UNKNOWN.
- [ ] Assert each variant retains all 41 prepared input paths and the same Target digest, and identify exact changed source evidence. Record external unresolveds/decorators and actual verdicts; commit/review.

### Task 12: Put full projects first in the gallery

**Files:** modify `fixtures/architecture_demo.py`, `tools/report_pages.py`, `tools/report_browser.py`, `docs/architecture-demo.md`, `README.md`; tests `tests/test_report_pages.py`, `tests/test_report_browser.py`, and three project-demo test files.

**Interfaces:** consumes accepted base/FAIL/UNKNOWN reports from Tasks 6, 8 and 11. Uses existing `demo-uml`, `report-pages`, and `report-browser` targets.

- [ ] Add three named Project journey entries ahead of technical cases, each with source pin/scope, connected feature, Target depth and evidence limits linked to its canonical report.
- [ ] Group each project's three source-only variants under it. Keep existing PASS/FAIL/UNKNOWN controls labeled as rule fixtures, and `I-flutter-shop` explicitly as a smaller runnable control.
- [ ] Extend browser acceptance to exercise desktop and mobile As-Is, Target and non-null Diff at nested component/library/class/member/source evidence. Verify overview/detail links, keyboard focus, selection and overflow; button presence or screenshots alone do not pass.
- [ ] Run `make report-pages` and `make report-browser`; record navigation receipts and commit/review.

### Task 13: Final verification, merge and handoff

- [ ] Run affected snapshot, collector, comparison and project-demo tests; then `make lint`, `make typecheck`, `make check`, `make against BASE=origin/main`, `make self-observation`, `make dart-native`, `make typescript-native SHELL=bash`, `make demo-uml OUTPUT=test-artifacts/full-project-demos`, `make report-pages`, and `make report-browser`.
- [ ] Inspect report payloads for exact source and Target hashes, input/library/module ownership counts, non-null comparison, truthful coverage/diagnostics, one architecture FAIL, one deep UML FAIL and the tested UNKNOWN transition per project. Record local results, final-head PR CI, Main CI and Pages publication separately. Do not claim app/device/backend execution.
- [ ] Measure runtime/cost and report actual limitations. Do not weaken tests, scope or gates to meet a budget.
- [ ] Obtain independent final spec and quality reviews; fix in-scope findings and rerun affected checks.
- [ ] Commit and push after review; wait for clean exact-head CI, then merge under existing user authorization. Record merged SHA and final Main/Pages state.

## Research receipts

- `compass-full-target-feasibility.md` and `compass-target-intent.md`
- `python-project-demo-research.md` and `archkeel-python-reference/source-manifest.tsv`
- `typescript-project-demo-research.md` and the pinned `archkeel-typescript-reference/nest-mikro-realworld` snapshot
- `demo-gallery-audit.md`, `full-demo-plan-review.md`, and `archkeel-project-demos-spec.md`
