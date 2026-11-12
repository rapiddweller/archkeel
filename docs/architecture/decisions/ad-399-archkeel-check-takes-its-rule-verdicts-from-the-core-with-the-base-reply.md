# AD-399 archkeel check takes its rule verdicts from the core with the base reply

**Status.** Accepted. Epic #880, lead decision L-73 step 1. It follows AD-390 (next step,
review part E of #1094). The open PR #1101 holds number 398.

**What a baseline is for a verdict** (read from the Python code; `run.py` is `check/run.py`).

| Part | Python | Effect | This slice |
|---|---|---|---|
| Contract and inside contracts at the baseline commit | `run.py:93`, `observe_revision(declared_at=baseline)` | the rule rows of the candidate | ported: the shell reads them from Git at the baseline |
| Base reply (accepted commit) | `run.py:308` | `observation_complete`; the delta | ported: the core reads it soundly (point 3) |
| Lock check of the base | `run.py:318`, `verify_observation` | exit 2 | Python; the core does not start |
| Changed policy input, B against H | `run.py:184`, `config.py:306` | exit 2 | Python; the core does not start |
| Ratchets | `expectation.py:189`, `compare_ratchets` | exit 1 | not ported (#1103) |
| Guardrails: no new violation, cycle, unknown, edge | `_guardrail_failures` | exit 1 | not ported (#1103) |
| Selected changes, empty declaration (diff only) | `_match_selected_changes` | exit 1 | not ported (#1103) |
| Validation baseline of `report --baseline` | `report.py:570-601` | comparison rows only | no core part needed |

No rule kind of `check` reads a changed contract (a changed policy input stops the run) or the
diff. No Cut A rule kind reads the base or the expectation.

**Decision.**
1. Shared rows. `run_check` gives the rule rows of the candidate (`rule_assessments`, the call of
   `inspect_observation` and `report`). Without the switch the shell removes them, so no byte of
   the output changes and the core does not start.
2. Shell. `check` gets `--native-core`. The core runs only when `check` has exactly 2 replies:
   the first is the base, the second the candidate. The contract reader reads Git at the baseline
   commit (`read_committed`: a regular blob at a safe path, else the path stays missing), never
   the working tree. The shell compares the run status, the rows and the exit code
   (`1 if failures or FAIL`). A difference is an error with exit 2. A Python exit 2, a configured
   collector or a frame that names a part gives the Python result with one note. The rows are
   shown only when the core decides.
3. Core. Protocol `archkeel-core-check-2` replaces `baseline` with `base` (the reply bytes). The
   core reads the base in `core/src/base.rs`: the store must accept it, the trust function of the
   request kind (`stage_one_shell_trust`, the only one) must trust it, its profile must be the
   profile of the candidate, and its model must derive under the contract of the request. Else one
   reason `the base reply: ...` names the whole contract, so the run is never PASS. The request
   carries no verdict and no trust field of the base.
4. The parts of the expectation stay with Python in stage 1. They are not rule verdicts and can
   only add exit 1. The note of a decided run names them. As frame parts they would make every
   `check` run fall back, with the same output and no compared verdict.
5. `report --baseline` changes no status, row or exit code, so the request has no baseline field.
   A test runs a baseline with new violations against the run without it.
6. The frame reader refuses a repeated key, also a repeated rule id (#1099).

**Reason.** `check` is the merge gate. Its rule verdicts must come from the core before `ir` and
`check` can go. The candidate is decided under the contract at the baseline, so the working-tree
contract must not reach the core.

**Rejected.** The base verdicts from the caller. A second trust path for the base. The working
tree as the contract of `check`. A frame part for each expectation part (point 4). A base without
the model check: a base that the core cannot read would not be seen.

**Limit.** `check` exits 0 when the rules are UNKNOWN and nothing regresses ("Existing UNKNOWN
stays UNKNOWN on a passing revision check", `docs/reference.md`); the core keeps this. The shell
takes the expectation, Git and host failures from Python. Stage 2 for `check` needs #1103 and
#1095.

**Tests.** `tests/test_cli_native_core_check.py`, `tests/test_cli_native_core.py`,
`tests/test_cli_native_core_frame.py`, `native/core/src/base_tests.rs`,
`native/core/src/check_tests.rs`.
