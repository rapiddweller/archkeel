# AD-1090: Baseline 1.4.0 compares the three call and type budgets

Status: accepted. Part of #1919. Amends AD-546 and AD-466.

## Why

A baseline of schema 1.4.0 held only the budgets `cycle_edges` and `private_crossings`. The
core measures `calls_unresolved`, `typing_positions` and `untyped_private_accesses` (AD-548),
but the compare did not read them. A contract that declares `measurement_budgets` got the named
gap `contract_hygiene_not_ported` (`baseline.invalid`, `budget.exceeded`, `budget.unknown`).
The DATAMIMIC CE gate needs these checks.

## Decision

1. The compare reads the three budgets from a file of schema 1.4.0. The run value comes from
   `measure_facts`, so it exists only for a complete inventory. Else the run does not measure it:
   the gap `budget.unmeasured` (exit 2), never 0.
2. A budget above its ceiling is the difference `budget.exceeded`: state `drift`, exit 1. A budget
   below its ceiling is stale, as before.
3. A budget that the contract declares and the file lacks is the difference `budget.unknown`:
   exit 1. It is not a gap, because exit 2 is green for CE, and deleting the line from the file
   would hide a grown measure. If the run does not measure it, the gap is `budget.unmeasured`.
4. A file of schema 1.0.0 to 1.3.0 keeps its numbers from release 4.0.1. They are not compared. The
   gaps `baseline.older_schema` and `baseline.budget_of_older_schema` stay as before.
5. A damaged file keeps `baseline.invalid` (exit 1). It already was ported.
6. `contract_hygiene_not_ported` no longer names the budgets. A run that declares
   `measurement_budgets` and holds no baseline file gets the named row `budget.unknown`, because
   nothing compares the declared budgets. A run that writes a baseline, or compares with a
   checked file, gets no such row.
7. The writer writes each measured budget. A budget that the run does not measure is not written.

## The pair `FAIL` with exit 2

With a current baseline the result can read `status: FAIL` and `exit_code: 2`. Decision: keep it.
The status names the worst verdict of the run. The exit code names the gate (AD-731). With state
`current`, every violation of the run is accepted debt (a new one is `drift`, exit 1), and exit 2
only says that an UNKNOWN stays open. The text keeps both words. Proof: a new violation or a
grown budget gives `drift` and exit 1, never `current`.

## Not done

- The amendment file of the project is still not read (AD-546).
- The CE file of release 4.0.1 holds numbers of another analyzer. It stays a gap until written again.

## Checks

`native/core/src/baseline_tests.rs`, `tests/test_cli_baseline_budgets.py` and
`tests/test_cli_core_contract_hygiene.py`.
