# AD-808 The package of a Dart scan is the nearest pubspec above its roots

**Status.** Accepted. Part of #880, closes #1539. Amends AD-454 rule 2 and AD-800.

**Reason.** The survey read the `pubspec.yaml` of the snapshot root as the package. In a pub
workspace (flutter/samples), the snapshot root holds the workspace root and the app is a member
below it: the member became a nested package (`DartNestedPackage`), and no rule was decided.

**Decision.**

1. The package of the scan is the nearest directory at or above each scan root that holds a
   regular `pubspec.yaml`, when every scan root has the same one. Otherwise the snapshot root
   stays the package, and each package file between it and a scan root keeps its gap.
2. The own `package:` URIs name files below `<package>/lib`. Module names stay relative to the
   scan root.
3. A member (`resolution: workspace`) reads the nearest `pubspec.yaml` above its directory as the
   workspace root (`native/dart/src/import_survey/workspace.rs`). The root must list the member
   in `workspace:`. Each other member `pubspec.yaml` must be readable, hold no scan root and have
   no `pubspec_overrides.yaml`. Then:
   - the workspace root does not become the package and gives no `DartNestedPackage`;
   - each member name and the root name are local packages: an import of one gets
     `DartLocalPackage`;
   - a name that a member declares with a local origin is local too;
   - the overrides of the root apply to the member.
   Each read `pubspec.yaml` is an input of the reply.
4. A workspace that the survey cannot read keeps the AD-800 rule: each `package:` import is a gap.
   A package file above the package that is no such workspace root keeps `DartNestedPackage`.
5. For a package below the snapshot root, each `.dart_tool/package_config.json` at the package
   directory or above is a whole-scope `DartPackageConfig` gap: the survey does not read it there.

**Truth.** Dart 3.12, `dart pub get --offline` and `dart analyze` on an app in a workspace: no
issue. The package configuration maps `package:other` to the member (`rootUri` `../other`).

**Plants.**
- `tests/test_cli_native_dart_packages.py`: an app in a workspace gives PASS when acyclic and FAIL
  with a cycle. An import of a member gives `DartLocalPackage`. Nested packages without a
  workspace keep `DartNestedPackage`.
- `survey_package_tests.rs`: a member with a local dependency, an unlisted app, a missing member
  `pubspec.yaml`, a member overrides file, and scan roots in two packages.

**Effect.** J-compass with the flutter/samples workspace root `pubspec.yaml` and the 36 member
`pubspec.yaml` files at 5541c59, and the app at `compass_app/app`: complete scope, 0 gaps, all 6
`REQUIRES-COMPLETE` rules PASS. The UML row waits for Dart symbol facts (#1533). The fixture as
pinned (no workspace root) keeps 105 import gaps.

**Rejected.** The workspace root as the package: the member is the package that `pub` builds,
and its own URIs name its `lib`.
