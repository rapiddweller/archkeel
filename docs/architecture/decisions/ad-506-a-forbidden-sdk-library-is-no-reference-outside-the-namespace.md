# AD-506 A forbidden SDK library is no reference outside the namespace

**Status.** Proposed. Part of #880. It extends AD-466 and AD-468.

**Decision.**
1. The hygiene check `reference.namespace` skips the `target` of a `forbidden_dependency` rule when the
   target is an SDK library of the profile. Release 4.0.1 does the same (`ir/profiles.py`
   `sdk_libraries`, `check/validation/references.py`).
2. The SDK libraries are a pinned list of the store: `archkeel_store::sdk_libraries(profile)`. The Dart
   profile has 22 names (`dart.async`, `dart.io`, `dart.web_gl` and the others of release 4.0.1).
   Each other profile has none. The scan request gives the list to the hygiene check; a dual-run or
   check request gives an empty list.
3. Only the exact name is exempt. `dart.nothing`, `dart`, a name of another family and the
   `allowed_dependency` target `dart.io` stay `reference.namespace` defects. The core is as strict as
   release 4.0.1 here, and stricter for an `allowed_dependency` target of an SDK library (4.0.1 holds it too).
4. No verdict changes by this exemption alone: the core already decides `dart.io` rules. The gap
   that held `G-dart` is gone. `fixtures/matrix.json` drops `reference.namespace: 1` from `G-dart`.

**Reason.** `fixtures/G-dart` forbids `dart.io` for its domain. Release 4.0.1 gives 9 PASS and 1
UNKNOWN for it. The core gave a `reference.namespace` gap for a name that no scan lists as a module,
and that gap kept the run from PASS.

**Rejected.** Exempting each first part that is standard (`dart`): it also exempts `dart.nothing`, a
typo that 4.0.1 holds. A language name in the core: the list lives in the store, which names profiles.

**Limits.** Other `G-dart` causes stay: the interface lifecycle checks (`interface.*`) are not ported
and the profile cannot decide `INTERFACE-BOUNDARY` (see the decision on stated profile limits).

**Tests.** `tests/test_cli_dart_sdk_reference.py` (fixture, three SDK names, four names that stay a
defect) and `hygiene_refs_tests.rs::a_forbidden_sdk_library_is_no_reference_outside_the_namespace`.
