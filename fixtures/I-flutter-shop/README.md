# Flutter shop architecture demo

This Flutter fixture models one shop journey: load a three-item catalog, add products, edit a cart, place an order, then list and open orders. It uses Flutter widgets, ChangeNotifier, a deterministic async backend, and an in-memory cache. Offline catalog and order reads use cached values; failed checkout preserves the cart for retry. It has no HTTP server, durable database, payments, auth, plugins, or generated app code. Run `make flutter-demo-check` from the repository root to fetch SDK packages, format-check, analyze, run widget tests, and build the web app under `test-artifacts/flutter-demo/web`.

Replay the unchanged Target through the ordinary architecture command:

```sh
make demo-architecture VARIANT=flutter-shop OUTPUT=build/flutter-shop.json
```

`make flutter-demo-check` verifies Dart analysis, Flutter widget tests, and a web build. It does not verify Android/iOS device behavior or native plugin integration.

The independent Target is in `architecture-contract.json` and mounted contracts; `docs/target.md` records ownership, source paths, and intended evidence. The app uses a `StatefulWidget`: its private `State` owns route construction and disposes all three view models plus the injected `MemoryStore`; the store closes its owned stream. The marked component graph in `docs/target.md` is the **baseline observed import graph** and is validated separately from the authored `requires` permissions; composition may use `state`, but no direct composition-to-state import is present.

Reference research is limited to the linked, pinned source slices: [Flutter Compass](https://github.com/flutter/samples/tree/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/compass_app), [Flutter Architecture Samples](https://github.com/brianegan/flutter_architecture_samples/tree/d898d1329e04e5b5fbdef1285b39ef975a6b8efa), and [Ente Auth](https://github.com/ente/ente/tree/6c853a7b676f9a910564c9efe0e38bde0d2b1871/mobile/apps/auth). Ente Auth is AGPL-3.0 and was read as reference only; no code or assets are copied. The demo selects smaller original flows rather than matching production breadth.

Dart shared UML does not express final/sealed modifiers, generic bounds, mixin-specific semantics, callback execution, or runtime state transitions. The Target closes domain and state member inventories, keeps selected widget/view-model inventories open with a stated limitation, and requires Flutter inheritance even where resolution is unavailable.

## Evidence matrix

| Dimension | This fixture | Pinned reference comparison |
|---|---|---|
| Structure | 21 original Dart modules across composition, nested shopping/orders UI, domain, data, and generic state. | [Compass](https://github.com/flutter/samples/tree/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/compass_app) has separate entrypoints, provider graphs, GoRouter routes and multiple connected booking features. [TodoMVC](https://github.com/brianegan/flutter_architecture_samples/tree/d898d1329e04e5b5fbdef1285b39ef975a6b8efa) compares several state approaches around a deliberately small todo domain. |
| Runtime flow | Async catalog/cache fallback, cart checkout, typed order stream, view-model disposal, and one Flutter lifecycle owner. | [Ente Auth](https://github.com/ente/ente/tree/6c853a7b676f9a910564c9efe0e38bde0d2b1871/mobile/apps/auth) includes encrypted SQLite state, remote diff sync, event-driven refresh, import, platform plugins and desktop integrations. |
| Static evidence | Native Analyzer facts feed the shared Core graph and ordinary report comparison. Base report: 100 Target relationships (87 UML, 13 component permissions), 821 assessments (786 PASS, 35 UNKNOWN), no UML FAIL; all six `complete_requires` receipts PASS. The 28 required journey edges are a reviewed subset, not the full Target graph. | The pinned Compass counterprobe selected the same 111 Dart files and 112 manifest inputs; source SHA-256 is `c6c1b8fe62fbc950af3b3dc4a033cac300bdeec2564e563909504a69df753e72`. After the Analyzer fix, 492/1,526 calls resolve, 1,034 remain unresolved, and 45 coverage diagnostics keep the report incomplete. |
| Dart constructs | Generic state, futures, typed streams, enum literals, named factory and Flutter inheritance are represented where facts allow. | Compass also uses sealed generic results, command abstractions, typedefs, pattern switches, generated `part` files and Freezed mixins. Ente adds factories, typed events, stream subscriptions, extensions, and platform/plugin boundaries. |
| UNKNOWN and unmodeled | Inferred local annotations, direct `main` binding reads, framework `State.widget`, Flutter SDK endpoints, dynamic dispatch, callback tear-offs, and factory-call identity remain UNKNOWN; extension declarations currently cause an explicit coverage gap. | These limits are about observed syntax/model boundaries, not proof that the corresponding runtime behavior is absent. Production routing, sync coordination, encrypted persistence, plugin conditionals and generated/localized output are outside this demo. |

The 35 base UNKNOWNs are 9 inferred binding annotations, 8 direct `main`-to-binding references (the collector records initializer binding-to-binding references and separate construction facts), 4 `State.widget`-mediated disposal calls, 1 checkout callback tear-off, 1 factory call projected to its class, 10 Flutter SDK endpoints, and 2 stream/subscription endpoints. `Order.Order.fromCart` follows the reviewed `Class.Class.named` identity convention; the remaining factory gap is the call target, not that qualified name. Do not filter unresolved built-in type syntax and claim this proves the missing direct binding edges.

Source was inspected at immutable commits; no reference implementation, assets, or generated code were copied. Ente Auth is AGPL-3.0. Future expansion should add one original slice at a time (for example, sync coordination and event handling) and keep plugin/runtime behavior UNKNOWN until its relevant source graph is actually scanned.
