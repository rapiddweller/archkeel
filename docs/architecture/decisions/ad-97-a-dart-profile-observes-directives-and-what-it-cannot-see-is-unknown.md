# AD-97 A Dart profile observes directives, and what it cannot see is UNKNOWN

## Decision

`[scan] language = "dart"` collects directive headers from in-scope `*.dart` files,
using the Dart lexer/directive/library modules and shared observation functions.
`ir/profiles.py` owns profile capabilities for collection and measurement.

| Case | Result |
| --- | --- |
| `import`/`export` with `show a, b` | one record per name, `symbols_known: true` |
| no `show`, including `hide` only | one record, null symbol, `symbols_known: false` |
| undecidable interface/target-symbol rule | `interface_symbol_limit` / `dependency_symbol_limit`, UNKNOWN |
| `symbol_placement`, `boundary_types`, `forbidden_construct`, `context_roots`, unmeasured budgets or AD-99 interface budgets | `rule_unsupported_by_profile`, exit 2 |
| typing, call, private-crossing/private-access scalars | null, compared as n/a |
| symbols, references, bindings | null; dependent claims UNKNOWN |
| invalid grammar/URI/part/id/pubspec namespace | `parse_error`, exit 2 |

Python imports add `symbols_known: true`; other Python behavior is unchanged.

## Why

No-show imports prove edges, not names. Module-level rules can decide them;
name rules report UNKNOWN, counted by AD-92. A small closed grammar needs no
Dart SDK and keeps one wheel. Ignore untracked `package_config.json` to preserve
snapshot resolution: own imports use `package:<namespace>/`, checked by pubspec name.
Keep generated files because their imports are real edges.

## Rejected

SDK/native parsers add dependencies for symbols this profile does not claim.
Treating no-show imports as every-name usage would invent violations.
Dart's stdlib is `dart`, not Python's module set.

## Limit

Directives show imports, not usage. Conditional alternatives all count as edges.
`init` needs explicit `--source` and `--namespace` for Dart.

## Check

Dart profile/config/directive/rule/UNKNOWN/false-positive tests cover grammar,
URIs, parts, unsupported rules and null scalars. They require PASS/FAIL for decided
rules, no hidden-crossing PASS and no invented part/deferred/conditional violations.
`fixtures/G-dart`, the Dart catalog and `make demo-dart` demonstrate the profile;
self tests and validation retain the committed unknown-position budget.
