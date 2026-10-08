# Task 5 report: Dart UML source-facts demo

## Result

Added five source-only Dart UML cases: matching Target, signature mismatch, missing enum member, forbidden nested dependency, and partial relationship resolution. Every case materializes the same Target and provenance bytes. `make demo-uml` retains Python and TypeScript cases and checks the CLI exit plus separate rule and UML verdicts.

The shared browser/report flow now covers root → nested component → module → class → member and back, with scope receipts, evidence, selection, path identity, and immutable payload assertions. There is no Dart-specific graph or renderer. Legacy Dart assertions now reflect measured static counts and leave unsupported claims UNKNOWN.

The existing G-dart forwarded `Key? super.key` parameters are explicit so the real Dart parser can represent their signatures. No collector completeness was reduced.

## Verification

All commands below ran with `DART_EXECUTABLE=/opt/homebrew/share/flutter/bin/cache/dart-sdk/bin/dart`, `DART_SUPPRESS_ANALYTICS=true`, `PYTHONDONTWRITEBYTECODE=1`, and `UV_CACHE_DIR=/tmp/archkeel-uv-cache` (except the direct parent compiler check).

```sh
make dart-native
make demo-uml OUTPUT=test-artifacts/dart-uml/suite
uv run --locked --with playwright==1.62.0 pytest -q tests/test_uml_demo.py -k 'shared_browser_acceptance and uml-dart-' --basetemp=test-artifacts/dart-uml/task5-browser
uv run --locked pytest -q tests/test_dart_profile.py::test_unmeasured_scalars_stay_null_and_static_claims_are_counts tests/test_dart_unknowns.py::test_unmeasured_scalars_are_null_and_measured_ones_are_counts tests/test_dart_unknowns.py::test_unmeasured_claims_stay_unknown_and_static_claims_are_counts tests/test_dart_unknowns.py::test_dart_observation_sections_it_does_not_observe_are_empty tests/test_dart_uml_acceptance.py::test_dart_demo_variants_keep_the_complete_target_unchanged
make demo-dart OUTPUT=test-artifacts/dart-uml/g-dart-check
make lint typecheck
make build
make smoke
uv run --locked pytest -q tests/test_report_pages.py
git diff --check
```

- Focused advisory and Target-immutability checks: **5 passed**.
- `make dart-native`: Dart format unchanged; `dart analyze` reported no issues; **83 passed** across profile, inner collector, unknowns, source facts, and Dart UML acceptance.
- `make demo-uml OUTPUT=test-artifacts/dart-uml/suite`: all 13 Python, Dart, and TypeScript rows matched their expected separate rule/UML outcomes. The forbidden-dependency row correctly has `declared_rules=FAIL`, `uml=PASS`.
- Browser acceptance: **5 passed, 14 deselected** for all Dart cases. Overview, nested component, UML/member and selected FAIL/UNKNOWN screenshots were captured and inspected.
- `make demo-dart OUTPUT=test-artifacts/dart-uml/g-dart-check`: exit 0; valid rows retain their measured FAIL/UNKNOWN statuses and malformed/unsupported rows are refused with exit 2.
- `make lint typecheck`: Ruff and mypy passed.
- Report gallery catalog: `pytest -q tests/test_report_pages.py` passed.
- `make build`: wheel and sdist built; strict Twine metadata checks passed.
- `make smoke`: the installed wheel and sdist each completed real Dart analysis and verified the scanned `sample.item.Item` identity independently of package name `smoke_app`.
- `git diff --check` passed. The architecture demo guide was regenerated from its catalog source.
- The parent independently compiled all five materialized variants with `dart compile kernel lib/main.dart`; evidence: `test-artifacts/dart-uml/compiler-check.txt`.

## Browser artifacts

All screenshots are under `test-artifacts/dart-uml/task5-browser/test_language_uml_demo_uses_sh*/`:

- `sh0`: `uml-dart-match-overview.png`, `nested-component.png`, `uml-dart-match-diff-member.png`
- `sh1`: `uml-dart-signature-fail-diff-member.png`
- `sh2`: `uml-dart-missing-member-fail-diff-cancelled.png`
- `sh3`: `uml-dart-forbidden-dependency-fail-diff-domain-edge.png`
- `sh4`: `uml-dart-partial-unknown-diff-pricing-method.png`

## Remaining gates

Local native execution used macOS with Dart 3.12.2. The new CI matrix still needs to verify Linux and Windows at the declared minimum Dart 3.9.0 and current 3.12.2, including Windows Make/native setup. Full repository `make check`, full report-page/browser suite, and self-observation/release checks remain parent integration gates.
