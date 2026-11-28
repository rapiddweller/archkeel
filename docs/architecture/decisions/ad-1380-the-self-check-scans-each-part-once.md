# AD-1380: The self-check scans each part once

Status: accepted. Follows AD-1350 (the facts cache). Replaces the targets `self-validate-native` and
`self-validate-shell` of AD-335 and AD-478. The gate rules of AD-1260 stay.

## Why

`make self-validate` ran three scans: `native/` (its gate), the shell (its gate) and then the system
run, which scans the shell, `native/` and the Studio UI again. On CI the repeated scan cost 112 to
166 s of a job that has 15 minutes. The PR gate runs the same target.

## Measured on main (db00750e)

One system run, the native run and the shell run, compared per part:

| Item | Result |
|---|---|
| Status of the part | equal (core UNKNOWN, shell PASS) |
| Rule rows: 92 of the core, 27 of the shell | equal, all rows |
| `explained` text of each rule | equal |
| Violation details and counts | equal (none) |
| Gap records of the core | the 13,062 records of the native run are all in the system result |
| Gap records of the system | 13,246 = 13,062 (core) + 0 (shell) + 184 (Studio UI) |

Gap records carry no part name, so a count per part is not read. No gate reads one.

## Decision

1. `make self-validate` is `make self-validate-system`: one run, with `--topology` and
   `--timings` (the timings are the sum of the parts). The targets for the native part and the shell
   part are deleted. To scan one part, run `archkeel report --config <its configuration>`.
2. `tools/self_check_gate.py` checks the result of the system run. For each part of
   `system.parts` it takes the rule rows of that part and applies the rules of AD-1260: it fails on
   a missing, empty, malformed or refused result, a rule without a row, a status that is not PASS,
   FAIL or UNKNOWN, a FAIL, a violation, or a counted violation that is not listed. UNKNOWN never
   fails. The message names the part. A result of `archkeel report --json` is still accepted.
3. The Studio UI part is now gated too. Before, no CI step gated it alone.
4. The old check of the exit code is kept for a result of `report --json`. A frame written by
   `--output` has no exit code; make accepts the exit codes 0, 1 and 2 of the run and the gate reads the
   file, which the target deletes first, so a stale file never passes.
5. `make self-check` prints the verdict of the system and of each part, and the measured groups from
   the system frame.

## Checks

`tests/test_self_check_gate.py` (a FAIL or a violation in one part, a part without rows, no
parts), `tests/test_make_self_check.py` (a refusal, an empty file and no file all fail the target),
`tests/test_self_check_summary.py`, `tests/test_cli_shell_self_check.py`.

## Not done yet

The system run reports no gap count for each part. A rule on one part's gap count would need the
part name in the gap record.
