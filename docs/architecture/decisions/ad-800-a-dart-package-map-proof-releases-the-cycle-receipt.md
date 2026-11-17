# AD-800 A Dart package-map proof releases the cycle receipt

**Status.** Accepted. Part of #880, closes #1535, Part of #1539. Amends AD-500 item 8 and the gap
table of AD-454.

**Reason.** A Dart `no_component_cycles` rule had no receipt (AD-500 item 8): a cycle can close
through a local package that the survey does not see. G-dart stayed UNKNOWN on its cycle rule, and
a path dependency or a workspace member held every rule of J-compass, even when no import used it.

**Decision.**

1. `pub` resolves a package name only from the root `pubspec.yaml` (dependencies, dev
   dependencies, overrides, workspace) and from `.dart_tool/package_config.json`, which `pub get`
   writes from it. The survey reads the root `pubspec.yaml` key by key into a package map
   (`native/dart/src/import_survey/package_map.rs`): each declared dependency is hosted, SDK,
   remote git (an `https`, `http`, `ssh`, `git` or `git@` URL) or local (a path, a local git URL,
   or a key that the survey does not read). An override replaces the dependency.
2. Each import of a package other than the own one keeps its record and gets a gap of its library
   when the map does not prove the package external:
   - `DartLocalPackage`: a local dependency, a member of the workspace that the root declares, or
     any package (the own one too) when the root has `resolution: workspace`: a workspace above
     the snapshot root can resolve or override any name;
   - `DartUndeclaredPackage`: no dependency declares the package and a local dependency exists. A
     transitive package is local only through the path of a local package: a hosted or SDK
     package cannot have a path dependency, and the path of a remote git package stays in its
     repository.
3. A local package or a workspace that no library imports adds no gap (#1539).
4. `.dart_tool/package_config.json` keeps its AD-454 check (`config.rs`): another package must lie
   outside the root. A pubspec that the survey reads only word by word, an unreadable workspace
   and a second package in or above a scan root keep their whole-scope gaps.
5. `proves_cycle_scope` is true for Dart: as for the other profiles, every way to miss a local
   package is a gap, and a gap holds the cycle rule through its effect (AD-634).

**Truth.** `dart analyze` (Dart 3) accepts the cycle plants without an error.

**Plants.**
- `tests/test_cli_native_dart_imports.py`: a single package, with a cycle FAIL and without one
  PASS. The gap table plants `DartLocalPackage` and `DartUndeclaredPackage`.
- `tests/test_cli_native_dart_packages.py`: each YAML form of a local package (also an override,
  a local git URL and a transitive package) holds the cycle rule. The AD-500 guard holds it where
  the proof is missing. The AD-500 tree without a local dependency gives PASS, and with a cycle
  FAIL.
- Collector tests: `package_map_tests.rs`, `survey_tests.rs`.

**Effect.**
- G-dart: 9/0/1 -> PASS 10/0/0.
- J-compass: 7 UNKNOWN as before. The cause is now 105 named import sites, not the whole scope.
- H-uml-dart and I-flutter-shop: unchanged (no Dart symbol facts, #1533).

**Open (#1539).** With the flutter/samples workspace root in the snapshot, the survey takes the
root `pubspec.yaml` as the package and gives `DartNestedPackage` for the member. The member as the
package of its scan root is the next step: no workspace member name matches a package that
compass imports.

**Rejected.**
- A blanket Dart receipt: a path dependency would close a cycle unseen (AD-500 B1).
- A whole-scope gap for each local package: it holds rules that no import of it can change.
