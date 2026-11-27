# AD-1231: A baseline that compares a declared budget within its ceiling decides it

Status: accepted. Closes #2162. Part of #1919. Amends AD-644 and AD-1090. This change can turn UNKNOWN into PASS.

## Why

A contract that declares `measurement_budgets` held the run UNKNOWN with the scope text "the profile cannot decide
declarations.measurement_budgets.<name>" (`limits.rs`, `UNMEASURED`). The text was true before AD-1090. Since
AD-1090 the core measures four of these budgets and `validate --baseline` compares them. A contract with declared
budgets could still never exit 0, also when every rule was PASS and the baseline was current. Measured: the fixture
of `tests/test_cli_baseline_budgets.py` and the CE copy `ce-23bd48d9` (the scope text named `private_crossings`).

## Decision

1. A declared budget is **compared** in a run when all of these hold: the request has `--baseline`, the file passed
   the check and has schema 1.4.0, it holds a ceiling for the budget, and the run measures a value that is at most
   the ceiling. The baseline code only lists the evidence (`baseline_frame::compared_budgets`). No name is matched.
2. The run assembly (`dual_run`) passes the list to the model as a setting (`Settings::with_compared_budgets`). The
   model decides: the profile limit of `limits::run_limits` skips a compared budget. The baseline decides no verdict. The run needs the graph to measure `private_crossings`, so
   the core derives the model one time, reads the budgets, and sets the settings again when one budget is compared.
3. A budget that is not compared keeps the hold: no file, a write alone, a file of schema 1.0.0 to 1.3.0, a budget
   that the file lacks (`budget.unknown`), a budget that the run does not measure (`budget.unmeasured`), and a value
   over the ceiling (`budget.exceeded`, `drift`, exit 1).
4. A write alone compares nothing, so it keeps the hold: nothing checks the file that it writes.

## Counter-examples (each is a test in `tests/test_cli_baseline_budget_hold.py`)

- A budget over its ceiling: `drift`, exit 1, status not PASS, the scope names that budget.
- A budget that the file lacks: `drift`, exit 1, status UNKNOWN, the scope names only that budget.
- An older file (schema 1.3.0): gap, exit not 0, status UNKNOWN.
- No file, and a write alone: status UNKNOWN.
- Two budgets compared and one missing: the scope names the missing one only.
- CE copy with the 1.4.0 baseline: 213 PASS, 62 UNKNOWN, 1 FAIL as before, exit 2, `current`. Only the scope text moves
  from the budget to the real cause (8 gaps of symbol records).

## Not done

- A run that is within the ceiling with no other hold reads PASS and exit 0: a contract can now reach exit 0. The
  UNKNOWN rules of CE still hold it at exit 2.
- The first derivation is not reused: a run that compares a budget derives the model a second time.

## Checks

`tests/test_cli_baseline_budget_hold.py`, `tests/test_cli_baseline_budgets.py`,
`tests/test_cli_python_profile_limits.py`.
