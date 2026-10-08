# Flutter shop Target

This Target is authored before app source. `shop` is the package and scan namespace; module identities are `shop.` plus the path under `lib/` without `.dart`. Component ownership follows composition, presentation → shopping → catalog/cart, and sibling domain/data/state areas. The module inventory below is complete for the planned fixture; every listed module has its declaration inventory and provenance in the mounted UML contracts.

## Source layout

| Component | Planned source | Responsibility |
|---|---|---|
| Composition | `lib/main.dart` | Initialize shared dependencies and start Flutter. |
| Composition | `lib/app/shop_app.dart` | Compose MaterialApp and own the app route table. |
| Presentation / shopping / catalog | `lib/presentation/shopping/catalog/catalog_page.dart` | Render products and request cart or order navigation. |
| Presentation / shopping / catalog | `lib/presentation/shopping/catalog/catalog_view_model.dart` | Load cache/network state, retry, and stop late updates after disposal. |
| Presentation / shopping / cart | `lib/presentation/shopping/cart/cart_page.dart` | Edit quantities, show totals, and retry checkout. |
| Presentation / shopping / cart | `lib/presentation/shopping/cart/cart_view_model.dart` | Own cart, in-flight submit guard, and disposal guard. |
| Presentation / orders | `lib/presentation/orders/orders_page.dart` | Render order history and open detail. |
| Presentation / orders | `lib/presentation/orders/order_detail_page.dart` | Render one immutable order snapshot. |
| Presentation / orders | `lib/presentation/orders/orders_view_model.dart` | Load orders, subscribe to changes, and cancel on disposal. |
| Domain / catalog | `lib/domain/catalog/product.dart` | Product identity, display name, and price in cents. |
| Domain / catalog | `lib/domain/catalog/catalog_repository.dart` | Async catalog read port. |
| Domain / cart | `lib/domain/cart/cart.dart` | Cart lines, quantities, and whole-cent total. |
| Domain / orders | `lib/domain/orders/order.dart` | Order snapshots, line snapshots, and enhanced status enum. |
| Domain / orders | `lib/domain/orders/order_repository.dart` | Async place/list/watch/lookup port. |
| Domain / checkout | `lib/domain/checkout/place_order.dart` | Reject offline checkout and coordinate one order. |
| Domain / checkout | `lib/domain/checkout/shop_status.dart` | Connection-mode port used by policy and presentation. |
| Data / repositories | `lib/data/repositories/cached_catalog_repository.dart` | Use the online backend or cached catalog. |
| Data / repositories | `lib/data/repositories/memory_order_repository.dart` | Submit orders and read cached/online order history. |
| Data / services | `lib/data/services/demo_backend.dart` | Deterministic async data, connectivity, and one-shot failures. |
| Data / services | `lib/data/services/memory_store.dart` | In-memory catalog/orders and typed order-change stream. |
| State | `lib/state/async_state.dart` | Generic typed loading/empty/ready/failed state. |

Composition owns the route table and creates catalog, cart, orders, and detail screens. The catalog journey is `main` → `ShopApp` → `CatalogPage` → catalog/cart view models → domain ports/use case → repository implementations → backend/cache. `CatalogViewModel` starts its initial load on construction; `OrdersViewModel` starts loading and subscribes on construction, so widget builds stay side-effect free. Orders continue through a typed `Stream<List<Order>>` from the cache to `OrdersViewModel`, and the selected immutable order is shown by `OrderDetailPage`. Composition uses positional constructor injection. `CartViewModel` owns a one-flight submit guard and disposed flag; `OrdersViewModel` owns/cancels its stream subscription; each async view model suppresses late updates after disposal. Domain and generic state classifiers have closed direct-member scopes. Widget/view-model scopes remain open only for framework/private presentation helpers; their required screen, command, state, and lifecycle members are still enumerated. Module call/import inventories are intentionally open because the Target asserts the user journey, not every incidental Flutter call or import.

## Ownership and permission policy

All component responsibilities, requirements, declarations, and edges cite this document and use `decided_by: agent`. `complete_requires` closes each component boundary. Presentation may use domain ports/use cases and generic state, but may not bypass repositories into data services. Data repositories may use data services and domain values; services remain below repositories. Domain components depend only on other domain components needed by the model (cart→catalog, orders→cart, checkout→cart/orders). Composition constructs the concrete graph and may depend on presentation, domain, data, and state.

The Target includes the required external `package:flutter/foundation.dart.ChangeNotifier` and `package:flutter/widgets.dart.StatelessWidget` inheritance endpoints, plus `runApp`. These SDK endpoints are referenced, not app-owned; unresolved Flutter SDK evidence remains UNKNOWN and must not be removed to make the report green. Shared UML has no traits for `final`/`sealed`, generic bounds, or mixin-specific behavior; callback execution and runtime lifecycle transitions are also not represented.

## Intended source-only checks

Keep this Target byte-identical across variants. These are planned mutations, not current findings or whole-report PASS promises.

| Variant | Source-only change | Expected comparison aspect |
|---|---|---|
| Base | Implement this inventory and journey. | Local module/member/call facts should compare; Flutter SDK inheritance can remain UNKNOWN. |
| Signature failure | Change `OrderLine.lineTotalCents` return type from `int` to `num`. | Deep `OrderLine.lineTotalCents` signature FAIL with source evidence. |
| Missing member | Remove unused `OrderStatus.completed`. | Closed enum-literal existence FAIL. |
| Forbidden dependency | Make cart presentation import/use `DemoBackend` directly. | `complete_requires` FAIL for presentation/cart → data/services. |
| Dynamic call | Resolve an order repository call through `dynamic`. | Required `OrdersViewModel` → repository call UNKNOWN, not a guessed edge. |
| Extension probe | Add a small `extension` on `OrderStatus` without changing the Target. | Record analyzer support/UNKNOWN; extension-specific semantics are unmodeled. |
