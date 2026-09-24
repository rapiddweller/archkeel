# AD-97 A Dart profile observes directives, and what it cannot see is UNKNOWN

## Decision

`archkeel.toml` may set `[scan] language = "dart"`. The analyzer then reads only the directive
header of every `*.dart` file under the scan roots (`embedded/dart_lexer.py`,
`dart_directives.py`, `dart_libraries.py`) and builds the observation with the same shared
functions the Python scan uses (`embedded/dart_scanner.py`). `ir/profiles.py` is the one table
of what each profile decides; the analyzer gates on it and `check` measures from it.

| Case | Result |
| --- | --- |
| `import`/`export` with `show a, b` | one record per name, `symbols_known: true`, decided like Python |
| without `show` (or with `hide` only) | one record, `symbol: null`, `symbols_known: false` |
| `interface_boundary` or `forbidden_dependency` + `target_symbol` it cannot decide | `interface_symbol_limit` / `dependency_symbol_limit`, UNKNOWN |
| `symbol_placement`, `boundary_types`, `forbidden_construct`, `context_roots`, a budget on an unmeasured scalar | `rule_unsupported_by_profile`, exit 2 |
| `typing_positions`, `calls_unresolved`, `private_crossings`, `untyped_private_accesses` | `null`, compared as `n/a` |
| `symbols`, `references`, `bindings` | `null`, so every claim built on them is UNKNOWN |
| header outside the grammar, unresolvable URI, orphan part, id collision, pubspec name mismatch | `parse_error`, exit 2 |

Python import records gain `symbols_known: true`; nothing else about a Python run changes.

## Why

Nothing the scanner cannot decide may read PASS, and nothing it is unsure of may read as a
violation. An import without `show` still proves the edge, so every module-level rule is decided;
which names it uses is unknown, so a rule about names reports UNKNOWN (AD-92 counts it).

- **Pure Python.** A directive header is a small, closed grammar. Reading it needs no Dart SDK
  in CI and keeps the analyzer one wheel.
- **No `package_config.json`.** It is ignored by Git, so the snapshots `check` materializes would
  resolve differently from the working tree. Own imports are exactly `package:<namespace>/`;
  the pubspec `name:` guards the namespace instead.
- **No generated-file exclusion.** `*.g.dart` and `*.config.dart` carry real imports; hiding
  them hides edges.

## Rejected

- **tree-sitter or `package:analyzer` now.** Either adds a native or SDK dependency for symbols
  the MVP does not claim. A later profile can fill `symbols` and turn UNKNOWNs into decisions.
- **Treating a no-`show` import as "uses everything".** That turns uncertainty into violations.
- **Reusing Python's standard library for Dart.** It would exempt `package:http` and `json`
  from `complete_external_scope`; Dart's is exactly `dart`.

## Limit

The profile sees imports, not uses: a symbol reached through an import without `show` stays
UNKNOWN until the source names it. Conditional imports count every alternative as an edge.
`init` does not detect a Dart package; `--source` and `--namespace` are required.

## Check

`tests/test_dart_profile.py` covers the grammar, URI mapping, parts, symbol UNKNOWNs, the
unsupported gate and null scalars. `tests/test_dart_config.py`, `test_dart_directives.py`,
`test_dart_rules.py`, `test_dart_unknowns.py` and `test_dart_false_positives.py` pin the same
behaviour from the specification alone: a PASS and a FAIL per decided rule, no PASS where a blind
spot hides a crossing, no violation from parts, deferred or conditional imports. The `dart-*` rows
of `fixtures/demo_catalog_dart.py` run on `fixtures/G-dart`, and `make demo-dart` prints them.
`tests/test_self.py` and `make self-validate` keep Archkeel's own contract and its
`unknown_positions` value.
