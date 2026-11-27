# AD-1261: The fixture matrix states intent and not observations

Status: accepted. Replaces point 2 of AD-462. Part of the drift-gates audit of 2026-11-27 (family C).

## Why

Each run of `fixtures/matrix.json` carried an `expect` block: exit code, status, counts of rules, the
scope text and the gap kinds. A test compared the core result with it. These are observations of the
current core, not promises. Any precision gain or new gap kind changed a number, and the author
edited the number to make the test pass (`99dc1ce95` changed only six scope strings).

## Decision

1. The 43 `expect` blocks are deleted. A run keeps its recipe (root, command, config, contract, plant)
   and its scenario intent (`section`, `intent`, `about`, `blocked_by`).
2. `tests/test_cli_fixture_matrix.py` runs each project through the release core. Each run must give an
   answer with a status and its exit code. A run with an intent and no `blocked_by` must give exactly
   that status.
3. The gallery shows the observations (counts, scope, gaps) as before.

## The truths that the old pins asserted, and where they are tested now

| Old pin | Truth | Test now |
|---|---|---|
| 13 runs: FAIL | a planted violation FAILs and never PASSes | `test_the_release_core_gives_each_project_its_stated_intent`; each plant also has its own test (`test_review_demo_identifies_the_forbidden_import`, the false-PASS probes) |
| 10 runs: PASS | a clean demo PASSes | the same test |
| 9 runs: UNKNOWN | a sound hold stays UNKNOWN | the same test; `test_module_cycle_demo_explains_its_rule`, `test_review_demo_keeps_an_open_binding_unknown` |
| 2 runs: PASS intent, UNKNOWN today | a named blocker | `blocked_by` (the test accepts the difference) |
| 9 test fixtures: UNKNOWN | the core answers | the test checks status and exit code |
| counts, scope text, gap kinds | none: observations | the gallery; `test_the_scope_line_counts_the_gaps_that_the_report_lists` keeps the one relation |

## Limit

A precision loss on a clean demo (PASS to UNKNOWN) without a blocker still fails: the intent is the
promise. The fix is the core or a named `blocked_by`, never a new number.

## Checks

`tests/test_cli_fixture_matrix.py`, `tests/test_report_gallery*.py`.
