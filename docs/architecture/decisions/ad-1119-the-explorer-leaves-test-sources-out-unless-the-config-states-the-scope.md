# AD-1119: The Explorer leaves test sources out unless the config states the scope, and the core holds the verdict

Status: accepted. Part of #874. Amends AD-313.

## Why

Test code in a source root adds test-only calls and components to the Explorer view. `scan.exclude_test_sources` exists
since AD-313, but its default is `false`. A project that never set the key sees its tests in the Explorer. `archkeel init`
already writes `exclude_test_sources = true`, so only a hand-written config had the problem.

A first design only left the files out. Then the Explorer verdict could read PASS where `validate` reads FAIL: a file that the
naming rule takes for a test (`protocol.test.ts`, `test_result_exporter.py`) can hold the only violation. Agents read the
`verdict` answer as a verdict, so that is a false PASS.

## Decision

1. For a Python or TypeScript scan that the Explorer requests, `archkeel-collect` sets `exclude_test_sources = true` when
   the config does not state the key (`Config::test_scope_set`). The scan keeps `Scanned::implicit_test_exclusion`.
2. When that implicit scope removes at least one file, the core holds the whole contract (`Scanned::test_scope_hold`,
   `hold_contract`): the run is UNKNOWN with the gap kind `implicit_test_exclusion` and the text "implicit test exclusion
   hides N files (...)". The core decides, not the shell. The verdict never reads PASS where `validate` reads FAIL.
3. A stated scope (`exclude_test_sources = true` or `false`) gives no hold. The view then has the ruling of the same scan that
   `validate` makes with that config.
4. `validate`, `report` and `check` keep the config as it is: tests included by default.
5. The Explorer snapshot (format 7) stores the excluded paths. The `verdict` answer gives `excluded_sources` (a count),
   `excluded_paths` (cut by the byte bound, `excluded_paths_cut`) and a `scope` note. A snapshot of an older format says `null`.
6. Rust and Dart keep the config as it is. Their test rules differ.

## Effect

An Explorer on a project with test files and no stated scope shows UNKNOWN until the config states the scope. The held
contract shows no violation rows. This is the price of a view that cannot read PASS by mistake. `archkeel init` writes the key,
so an initialized project is not held.

## Not done yet

- The view could hide test modules in the display only and keep the full ruling. That needs the collector to name the test
  files without removing them, and a filter of the topology. Not built.
- The test rules use naming conventions. On a copy of DATAMIMIC CE the default left out two production files by name
  (`test_result_exporter.py`, `data_mimic_test.py`); the Explorer verdict reads UNKNOWN and names them.
- The Studio browser view shows no count yet. The public collector stream carries no list (see #874).

## Checks

`native/collect/src/lib_tests.rs` (default, explicit false, explicit true, the hold) and `tests/test_explorer_verdict.py`
(a TypeScript project whose `protocol.test.ts` holds the only violation: `validate` FAIL, implicit view UNKNOWN, stated scope:
the view equals `validate`).
