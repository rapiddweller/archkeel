# Compass whole-app Target

This Target covers all 89 logical libraries from the pinned Compass application. Its five architecture areas are application composition and routing, presentation, domain, data, and shared utilities. Presentation is grouped by login/logout, home, search, results, activities, booking, and shared UI. Data is grouped by repository family and API, local-data, token-storage, and serialized-model services.

The expected journey is: environment setup → auth-aware route selection → search form and saved itinerary → destination results → activity selection → booking creation and persistence → booking detail/share or home history. Repository ports remain in the data subtree because that is where this sample declares them. Dependencies reflect these source boundaries; the Target does not invent a stricter layered design.

Each source library has one component owner. The 22 generated `.freezed.dart` and `.g.dart` inputs remain in the source inventory and are attributed to their model library. They are not separate modules. Each Freezed API mixin is a closed contract for its model property getters, JSON serialization method, and typed `copyWith` getter. Generated implementation and CopyWith helper classes are outside that principal API.

Principal contracts cover auth/session, search and itinerary state, result/activity selection, booking creation/detail/share, home booking summaries, repository ports, API/local/token services, immutable data models, and generic `Command`/`Result` utilities. Widget/framework inheritance and external runtime behavior remain outside this Target. Open module scopes leave unlisted helper declarations and incidental calls unresolved; named contracts and their relationships are the intentional architectural comparison surface.

Source input digest: `c6c1b8fe62fbc950af3b3dc4a033cac300bdeec2564e563909504a69df753e72` (111 Dart files; `pubspec.yaml` is configuration, not a module).

Target bundle SHA-256: `a522b5072a4cb3ce1a70e7aebeeea5cbf516e552a313e3cc845b5272a5c1c772`
