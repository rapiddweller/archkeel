# Final fix wave

## Root causes and changes

- `snapshot.dart` used only the pubspec SDK lower bound to stage package language and never checked whether the running Dart SDK satisfied the full range. Incompatible and malformed ranges now create `SdkConstraintError` coverage gaps and skip those sources; supported ranges retain their lower-bound language version.
- `collector.dart` filtered only syntactic diagnostics. It now uses Analyzer diagnostic codes for malformed, unsupported, illegal, and inconsistent language overrides; affected libraries get a `LanguageVersionError` gap and no declaration inventory. `RuntimeInfo.required` remains the native collector's `>=3.9,<4` requirement.
- Added real-process tests for incompatible/future SDK ranges, malformed constraints, future/malformed overrides, and supported 3.9/2.19 overrides. Added a CLI/Core control asserting unsupported language input cannot produce aggregate PASS.
- The SDK range regression derives compatibility from `facts.runtime.version`: `>=3.9.0 <3.10.0` is accepted when the actual runtime is within that range (including CI's 3.9 leg) and rejected above its upper bound; `>=3.99.0 <4.0.0` is rejected for configured 3.9/3.12 versions. Added and verified a library/part override mismatch control.
- Windows TypeScript and Dart native matrix setup steps now run the POSIX `dart-setup` recipe under Bash. Main-only matrix triggers remain unchanged.

## Verification

- RED: focused native regression run before the fix: `4 failed, 2 passed, 23 deselected`; both project SDK ranges and the future inline override reproduced false `full_scope=True`. The malformed override control initially used a comment Analyzer does not recognize as an attempted override; it was corrected to Analyzer's recognized malformed `3.x` form before the green run.
- GREEN: focused process and CLI controls: `8 passed, 50 deselected`; final portable CLI-only rerun: `1 passed, 27 deselected`.
- `DART_EXECUTABLE=/opt/homebrew/share/flutter/bin/cache/dart-sdk/bin/dart DART_SUPPRESS_ANALYTICS=true make dart-native`: format and Analyzer passed; producer/acceptance suite `91 passed in 353.44s`.
- `make lint`: passed, 387 files formatted and Ruff clean.
- `make typecheck`: passed, 125 source files.
- Ruby YAML parse of `.github/workflows/ci.yml` and `git diff --check`: passed. No Windows or Main matrix execution was attempted.
- No D-self regeneration was needed: the Python source tree and its measured policy were unchanged.
- `make against BASE=05c56a18786d5d0e97e9725b06a435a9ae72c5f1`: passed after commit; the selector used the committed amendment (`amendment_status=valid`, `exit_code=0`, `widenings=[]`, `calls_unresolved=714`).
- Targeted runtime-aware range and part-mismatch rerun on Dart 3.12.2: `3 passed, 28 deselected`; test file Ruff format/check passed.

## Exact migration amendment

Generated with the existing `validate --against --write-amendment` path for base `05c56a18786d5d0e97e9725b06a435a9ae72c5f1`, current recursive policies, and baseline 714. The v2 amendment is `docs/architecture/decisions/ad-211-dart-native-no-legacy-migration-amendment.json`.

- Before/after contract digests: `ccb13016bd6857a20552146753d1e025c8b4ce72c522a3e6d404340969dea171` / `47d5848f42a4a03fd2d824facb838b50387ee1cb5eac5955cdfb188cfe8ea6b9`.
- Before/after baseline digests: `cd7275afc0abb0e0dc7226fbca9f81c77257e422bfaf6438be5c7b3f1176e3eb` / `9d3089fc49400ab64dfd5ee2ab08e727690e088266cd6aa4c1b7af8a3c59b1f0`.
- Attribution: `Implementing agent (recording user-approved native/no-legacy migration plan)`. The rationale records the four authorized changes: Dart source facts/responsibility to the native analyzer package, `entry` ownership/responsibility to `archkeel.analyzer.dart`, and removal of the obsolete source component. No review or authenticated approval is attributed to the implementing agent.

## Remaining gates

- Linux/Windows and minimum/current Dart matrix results remain CI-only; the parent owns full repository, browser, demo, and build-smoke acceptance.
