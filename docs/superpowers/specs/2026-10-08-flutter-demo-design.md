# Flutter demo: representative structure and honest limits

User-authorized continuation of the Dart UML demo, 2026-10-08. No legacy compatibility is required. Existing G/H fixtures remain focused regression controls; the new runnable app lives in `fixtures/I-flutter-shop`.

## Outcome

Demonstrate one connected Flutter journey and an independent Target from responsibilities through nested components to UML. Compare the chosen structures against pinned GitHub examples, then measure ArchKeel's support and gaps. File count is not a realism metric. This is a representative application slice, not a claim to reproduce production scale or mobile platform integration.

## Reference evidence

- [Compass](https://github.com/flutter/samples/tree/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/compass_app): connected routes, views/view models, repositories/services, generic async results, generated models. Instructional application.
- [Flutter Architecture Samples](https://github.com/brianegan/flutter_architecture_samples/tree/d898d1329e04e5b5fbdef1285b39ef975a6b8efa): alternative state management and shared repository contracts. TodoMVC comparison, not production complexity.
- [Ente Auth](https://github.com/ente/ente/tree/6c853a7b676f9a910564c9efe0e38bde0d2b1871/mobile/apps/auth): production lifecycle, streams/events, local/remote persistence, factories, extensions, platform and workspace packages. Read as reference only; copy no AGPL source.

The demo is original code. Preserve precise source links, inspected scope and limitations in its short README. Analyze an unchanged pinned Compass source snapshot separately as a counterexample; never derive demo Target from that observation or silently omit unsupported files.

## Journey and boundaries

Catalog load → add a product → cart quantity/total → place order → orders list → order detail. Include loading, empty, error/retry and success states. Offline mode must visibly use a cached catalog/orders list and reject checkout; returning online permits retry without duplicate order submission. Async completions and stream subscriptions must respect disposal.

```text
shop (package and scan namespace)
├── composition: main, app wiring and navigation
├── presentation
│   ├── shopping
│   │   ├── catalog: view + view model
│   │   └── cart: view + view model
│   └── orders: list, detail + view model
├── domain
│   ├── catalog: Product
│   ├── cart: Cart / CartLine and totals
│   └── orders: Order / OrderLine / OrderStatus
├── data
│   ├── repositories: catalog cache and order coordination
│   └── services: deterministic async demo backend + local store/events
└── state: generic loading/result state shared by view models
```

Composition wires dependencies through constructors and owns Flutter routing. Presentation owns display state and commands; it may use domain, state and repositories, never service internals. Data repositories coordinate services and own caching; services do not depend on repositories or UI. Domain owns values/invariants and depends only on Dart SDK. State owns generic state values, not business policy. Close allowed directions with existing `complete_requires` at meaningful levels. Use two meaningful siblings under shopping; no empty depth wrappers.

Use Flutter's own ChangeNotifier/ListenableBuilder, Navigator and widgets; no Provider/BLoC/go_router dependency solely to mimic a reference. Use a deterministic async backend and in-memory cache, explicitly labelled as demo substitutes for HTTP/durable storage. No authentication, payments, cryptography, DB, server, generated app code or platform-plugin implementation. Their absence remains in the realism matrix.

## Target before source

Task 1 authors component ownership, responsibilities, permissions, planned modules/classifiers/members/signatures and required relationships before any `lib/*.dart` implementation. Agent-chosen decisions use `decided_by: agent`; do not claim the user authored individual directions. Every planned app module has UML inventory and provenance. Core business/state classifiers have complete direct member inventories; open scopes need a specific evidence limitation.

Required relationships include app-owned calls, direct construction/inheritance and at least one external Flutter inheritance relationship (for example a view model to ChangeNotifier). Do not omit an essential external relationship to obtain green. Shared UML cannot express every Dart trait: sealed/final modifiers, generic bounds, callback execution, mixin-specific semantics and runtime state transitions must be recorded as unmodeled, not silently counted as supported. A base demo may correctly be UNKNOWN overall while local domain/member assessments are PASS.

Keep identical Target bytes in all source-only variants: base, deep signature mismatch, missing unused enum literal, forbidden nested dependency, dynamic required call, and one extension/mixin probe. A FAIL must name its exact subject/aspect and source evidence. Unsupported declaration gaps must prevent false completeness; UNKNOWN must remain visible at parent scopes.

## Acceptance

- A normal Flutter package with a committed dependency lock, minimal web runner, `flutter analyze`, tests of the actual user journey/error/retry/disposal and a successful web build. A widget test is runtime proof inside Flutter, not emulator/device proof.
- Existing ArchKeel CLI, schemas, graph and report renderer; add catalog rows and one Make entry point. No second analysis pipeline or imported project dependencies during scans.
- Traverse root → presentation → shopping → cart → module → classifier → member in As-Is/Target/Diff at desktop and mobile widths. Show responsibilities, evidence, FAIL and UNKNOWN without losing context.
- Compare unchanged pinned reference inputs against the current collector and record exact file scope/digests, exit, diagnostics, gaps and unresolved sites. No external code execution or dependency installation for this probe.
- Report matrix: demonstrated static support / syntax-only support / explicit UNKNOWN or rejection / unmodeled runtime semantics / feasible follow-up. Do not claim full Flutter compatibility.
- Local checks first; no push, merge, publication, issue closure or CI launch.
