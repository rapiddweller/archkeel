# AD-1263: Golden replies are not compared, and resolution is tested directly

Status: accepted. Replaces the comparison of AD-343. Part of the drift-gates audit of 2026-11-27 (family C).

## Why

AD-343 froze the replies of the TypeScript collector before the Python collector was deleted. The old
collector was the oracle. It is gone. Since then `test_the_producer_equals_the_golden_reply` compared
today's native collector with a recording, and the recording was written again each time the output
changed, with a reason in `RECORDINGS.md` (28 entries for 15 cases). A byte-equal result of the same
producer proves no soundness. The Dart import survey was pinned the same way (edge lists and counts,
"equal to release 4.0.1").

## Decision

1. Deleted: the whole-reply equality, its comparator, recorder, allowance table, 14 recordings and
   digests, `make golden-record`, and the Python tests of that machinery (`test_collector_golden_replies.py`,
   `golden_*.py`).
2. Deleted: the live byte-equality of the validation table (`records_tests.rs`) and its writer.
3. Deleted: the Dart `fixture_edges/*.txt` lists and the survey counts of four fixtures.
4. Kept as input: `h-typescript.json.gz` and `validation.json` (ten tests of the store, model, eval,
   report and core decode them), `mounted-receipt/interface-plants.json`, the small sources.
5. Added: `tests/test_collector_native_ts_resolution.py` (9 projects) and
   `native/dart/src/import_survey/import_forms_tests.rs` (2 tests).

## The truth each golden case asserted, and where it is tested now

| Golden case | Truth | Test now |
|---|---|---|
| synthetic-paths-multi | path mappings: fallback list, longest match, `*`, `baseUrl` | `test_..._resolves_the_imports_as_typescript_does[synthetic-paths-multi]` (exact edges) |
| synthetic-nodenext | `.js` names `.ts`, `.cjs` names `.cts`, a CommonJS file cannot require an ES module | same test; `resolve_tests.rs` (`nodenext_resolution...`) |
| synthetic-bundler | asset import external, `@/*` maps, missing target unresolved | same test; `resolve_tests.rs` (bundler) |
| synthetic-tsx-paths | `.tsx`, `.cts`, `export from`, `import type`, `import()`, `require()` | same test |
| synthetic-allowjs | JS and JSX with `allowJs`; literal `require` resolves, computed does not | same test |
| synthetic-esm-forms | every ES import, export and dynamic form; missing and computed held | same test |
| synthetic-package-maps | `exports` hides unlisted paths; unsupported forms held or right, never guessed | same test; `resolve_tests.rs` (exports maps) |
| synthetic-gaps | a file that does not parse, a missing import and a computed global write are held | same test (status UNKNOWN and named gaps) |
| synthetic-script-namespace | a script namespace member is used across scripts; an unpublished member is held | same test |
| h-typescript, h-uml-typescript, f-typescript-story, l-nest-realworld | the fixture is decided as its intent says | `fixtures/matrix.json` intent test (the matrix states intent, not results) |
| excalidraw-math, excalidraw-laser-pointer | real code parses and resolves without a crash | `test_collector_native_scaling_real.py`, the script and syntax tests |
| Dart edge lists (4 fixtures) | each form of a Dart directive gives its edges | `import_forms_tests.rs`; `binding_tests.rs`, `package_tests.rs`, `plant_tests.rs` |
| validation table equality | the table is the table | none: the store validation reads it on every reply |

## Mutation check

Removing the second `paths` fallback of `synthetic-paths-multi` fails the resolution test on the
missing `shared.two.ts` edge.

## Limit

A form that the collector holds today (`export type *`, triple-slash references, `#internal`) is held
by the collector, not asserted: improving it does not fail a test. A form that it resolves to a wrong
file does.
