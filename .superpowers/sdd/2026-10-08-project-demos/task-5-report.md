# Task 5 — Compass Target

## Result

Authored the whole-app Target from the pinned Compass source and independent responsibility map. It covers all 89 logical libraries across application composition/navigation, presentation features, domain models and use cases, repository families, API/local/token services, and utilities. The 22 generated part files remain physical inputs owned by their 11 parent model libraries.

The composed graph contains 468 entities: 439 UML declarations (89 modules, 52 classes, 11 mixins, 7 enum/literal declarations, 7 functions, 270 methods/attributes, and 1 referenced symbol) plus 29 components. It has 56 relationships total: 21 `requires` edges and 35 UML relationships (11 `mixes_in`, 11 `realizes`, 6 `inherits`, and 7 `calls`). There are 24 nested components, 89 open module scopes, and 37 closed principal API scopes. Freezed mixin APIs declare their property getters, `toJson`, and typed `copyWith` getter. Repository ports/adapters, auth/session, routed ViewModels, booking, API/local services, route/provider composition, and generic `Command`/`Result` APIs are represented.

The Target was authored from pinned source declarations and the independent intent map. No SourceFacts collection or observed graph was used. Framework behavior, external inheritance, widget helper exhaustiveness, and incidental calls remain outside the closed API surface.

## Immutable identity

- Source: `flutter/samples` commit `5541c59ab8e9d7e74c1a35ef22bd43a487fc596c`.
- Source scope: 111 Dart inputs, 89 logical libraries, 22 generated parts; source digest `c6c1b8fe62fbc950af3b3dc4a033cac300bdeec2564e563909504a69df753e72`.
- Target bundle SHA-256: `67126434157544d3b3429fa6ea39a88721c6a23792bd801f44db41f4243750a7` (fix round 2).
- Upstream snapshot files were unchanged.

## Verification

- `uv run --locked pytest -q tests/test_compass_project_target.py tests/test_project_demo_snapshots.py` — 7 passed.
- `uv run --locked ruff check tests/test_compass_project_target.py` — passed.
- `uv run --locked ruff format --check tests/test_compass_project_target.py` — passed.
- `git diff --check` — passed.

The focused checks validate schema composition, unique ownership of every module, parent-part attribution, source-backed application and booking boundaries, required principal contracts, mixin and adapter relationships, and the frozen Target digest. No full project collection or acceptance comparison was run; that belongs to Task 6.

## Task 5 fix round 1

- Added `contracts/application.json` with separate environment/app-composition and route/navigation responsibilities. Its five composition modules and two navigation modules have distinct leaf ownership and source-specific duties.
- Added the exact `_createBooking` to `BookingCreateUseCase.createFrom` call obligation in the presentation contract. The domain operation remains declared in the domain contract and is represented here by a reference endpoint.
- Added regression assertions for the exact module partition, call endpoints, and referenced cross-contract endpoint.
- Target bundle SHA-256 after fix round 1: `17a34e8182418f1500442a965db85d6e694e55d7776754ea60f4c997f0667127` (superseded by fix round 2).
- Final fix-round commands/results are listed above; no full Compass collection was run.


## Task 5 fix round 2

- Corrected the root presentation package/namespace from `compass.presentation` to `compass.ui`, matching the pinned `lib/ui/**` source modules and nested `contracts/presentation.json` selectors.
- Corrected the root utilities package/namespace from `compass.utilities` to `compass.utils`, matching `lib/utils/**` and nested `contracts/utilities.json`. Other ancestor package scopes (`compass`, `compass.domain`, `compass.data`) remain source-aligned.
- Added `test_compass_nested_package_ownership_stays_inside_each_parent_component`; it failed on the old `compass.presentation` prefix and now checks every nested package and exact module against its containing root component.
- Updated the Target receipt digest to `67126434157544d3b3429fa6ea39a88721c6a23792bd801f44db41f4243750a7`. Task 6's in-progress test file still has the prior expected digest and is deliberately left out of this fix commit; refresh it before acceptance runs.
- Verification: `uv run --locked pytest -q tests/test_compass_project_target.py tests/test_project_demo_snapshots.py` — 8 passed. `uv run --locked ruff check tests/test_compass_project_target.py` — passed. `uv run --locked ruff format --check tests/test_compass_project_target.py` — passed. `git diff --check` — passed.
