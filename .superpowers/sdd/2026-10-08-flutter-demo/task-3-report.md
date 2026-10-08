# Task 3: Flutter app implementation

Implemented the authored Target as a runnable, SDK-only shop flow. The catalog has three fixed products; the app supports cart edits, online checkout, order history/detail, cached offline reads, retryable failures, and explicit app-lifetime cleanup. The initial implementation followed the pre-source Target; the reviewed fix round below makes narrow corrections to its contracts and documentation.

The six widget tests cover the full journey with a two-line `$9.47` order, empty order history, catalog loading/error/retry, cached offline catalog and order reads, failed checkout preserving cart, duplicate-submit protection, and mutation attempts during a controlled pending checkout. Quantity/add controls disable during submission, and view-model guards prevent late cart edits from being cleared with the submitted snapshot. The unmount test checks pending-load completion, stream cancellation, and store-stream closure. Tests use real Flutter widgets and controlled Futures, with no timing sleeps.

`make flutter-demo-check` passed using Flutter 3.44.8 stable (revision `058e0af2c2b57e369d905a03ac9748b0ebf543c6`) and Dart 3.12.2. Output included:

```text
Formatted 22 files (0 changed) in 0.02 seconds.
Analyzing I-flutter-shop...
No issues found!
00:00 +0: loads catalog, checks out, and opens the saved order
00:00 +1: offline cache and failed checkout keep the cart for retry
00:00 +2: catalog request errors can be retried
00:00 +3: ignores duplicate checkout taps while submission is pending
00:00 +4: unmount cancels the order stream and ignores pending loads
00:00 +5: All tests passed!
✓ Built ../../test-artifacts/flutter-demo/web
```

The first test-first run failed as expected because `lib/` had not yet been implemented; Flutter reported missing imports under `lib/data`, `lib/domain`, and `lib/presentation`. No full repository check, CI, or browser acceptance was run for this task. Flutter emitted its standard successful web-build Wasm dry-run notice; it did not block the build.

## Fix round 1 (base `0aa646aa`)

The two new regressions were first run against a temporary extraction of base `0aa646aa`, with only the updated widget test overlaid. Both failed for the intended reasons: after a failed online refresh, switching offline showed no `Trail Mix`; and while checkout was pending, returning to catalog left the add button enabled. Existing baseline widget tests passed in that run. The temporary extraction is at `/private/tmp/flutter-fix-round1-red`.

The fix routes online/offline changes through the repository-backed load path, so offline mode can restore the repository cache after a failed refresh. Catalog rebuilds listen to both catalog and cart view models, keeping add controls synchronized with checkout state. Constructor parameter names and public injected-state ownership now match Target signatures. The reviewed Target corrections are recorded in `docs/target.md`: remove unused orders injection from CatalogPage, declare catalog's required cart dependency and `_catalogBody` delegation, correct the factory identity, remove the implicit DemoBackend constructor requirement, and declare its private request-check helper. The fixture SDK floor is `>=3.10.0 <4.0.0`, matching the locked dependencies.

Structural contract tests passed: `.venv/bin/python -m pytest -q tests/test_flutter_demo.py` (`3 passed`). `git diff --check` passed. The final `make flutter-demo-check FLUTTER_EXECUTABLE=/opt/homebrew/share/flutter/bin/flutter DART_EXECUTABLE=/opt/homebrew/share/flutter/bin/dart` passed with Flutter 3.44.8 / Dart 3.12.2: format check (22 files, unchanged), analyze (no issues), all 6 widget tests, and web build to `test-artifacts/flutter-demo/web`.

The direct ArchKeel base report is `test-artifacts/flutter-demo/fix-round1-base.json`, generated with the worktree `.venv/bin/archkeel` and Flutter's bundled Dart SDK. It reports `observation_complete=PASS` (21/21 files read and parsed, AST coverage 100%, zero coverage failures). All 6 `complete_requires` assessments pass with zero violations. `declared_rules=UNKNOWN` because UML evaluation has no complete receipt: the UML assessment is `UNKNOWN` with 35 undecided facts, not FAIL. This is the baseline structural report, not UML acceptance. The 35 UNKNOWNs break down as 9 unavailable constructor-binding annotations; 8 unresolved `main` local-binding reads; 4 `State.widget`-mediated disposal calls; 1 `CartPage` checkout tear-off; 1 `PlaceOrder` factory call whose current native fact anchors to the class rather than the named constructor; 10 ambiguous Flutter SDK endpoints (`runApp` and widget/state/ChangeNotifier inheritance); and 2 ambiguous Dart SDK stream/subscription operations. Keep the named-constructor call UNKNOWN rather than widening collector scope here. No full repository gate, CI, or browser acceptance was run.
