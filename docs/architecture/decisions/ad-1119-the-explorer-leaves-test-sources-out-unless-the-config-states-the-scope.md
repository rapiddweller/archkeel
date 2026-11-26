# AD-1119: The Explorer leaves test sources out unless the config states the scope

Status: accepted. Part of #874. Amends AD-313.

## Why

Test code in a source root adds test-only calls and components to the Explorer view. `scan.exclude_test_sources` exists
since AD-313, but its default is `false`. A project that never set the key sees its tests in the Explorer. `archkeel init`
already writes `exclude_test_sources = true`, so only a hand-written config had the problem.

## Decision

1. For a Python or TypeScript scan that the Explorer requests, `archkeel-collect` sets `exclude_test_sources = true` when
   the config does not state the key (`Config::test_scope_set`). `exclude_test_sources = false` keeps the tests.
2. `validate`, `report` and `check` keep the config as it is: tests included by default. The governance scope does not change.
3. The Explorer snapshot (format 7) stores the excluded paths. The `verdict` answer gives `excluded_sources` (a count),
   `excluded_paths` (25 at most) and a `scope` note. A snapshot of an older format says `excluded_sources: null`.
4. Rust and Dart keep the config as it is. Their test rules differ.

## Effect

The Explorer verdict can differ from `validate` when a test source breaks a rule. The `verdict` answer names the left-out
paths, so the view never claims the full scope. A production import into an excluded test stays UNKNOWN (AD-313).

## Not done yet

- A production file that the naming rule takes for a test can hold the only violation. The Explorer verdict then reads PASS for the
  scope that it scanned. This is the rule of an explicit `exclude_test_sources = true` (AD-313) and stays a known limit: a strict
  xfail probe and `docs/known-limits.md` name it. The shell decides no verdict. A core-side scope hold is a later change.
- The test rules use naming conventions. On a copy of DATAMIMIC CE the default left out two production files by name
  (`test_result_exporter.py`, `data_mimic_test.py`); the answer lists them.
- The Studio browser view shows no count yet. The public collector stream carries no list (see #874).

## Checks

`native/collect/src/lib_tests.rs` (default, explicit false, explicit true, `validate` unchanged) and
`tests/test_explorer_verdict.py` (a test file with a layer break: `validate` FAIL, the view names the file).
