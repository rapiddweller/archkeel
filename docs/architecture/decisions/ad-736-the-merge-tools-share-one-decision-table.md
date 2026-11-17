# AD-736 The merge tools share one decision table

**Status.** Accepted. Part of #880, #1451 (Wave 4). Owner decision 2026-11-17: `tools/merge_check.py` stays. Visible change: `mergeable` UNKNOWN and pending checks are WAIT, no longer "resolve the conflict"; new exit codes and `--json`, `--wait`.

**Reason.** `tools/merge_pr.py` had its rules in one `if` chain: an UNKNOWN merge state read as a conflict, a queued check as "not success", and the status of a check was mixed with its conclusion. `tools/merge_check.py` warned "no PR CI by policy", which is false since AD-674.

**Decision.**
1. `merge_pr.decide(pr, required, runs)` returns MERGE, WAIT or REFUSE with reasons `{code, detail}`. WAIT: `mergeability_unknown`, `check_pending` (queued, in progress, pending, waiting). REFUSE: `not_open`, `draft`, `conflict` (CONFLICTING or DIRTY), `check_missing`, `check_failed` (completed with any conclusion but success, the conclusion named), `blocked`. BEHIND alone merges (AD-676). REFUSE beats WAIT.
2. `status` and `conclusion` of a check stay two fields. `--json` prints `{verdict, reasons, required: {names, source: protection|default}, head}`; `--wait N` loops every 10 s while the verdict is WAIT.
3. Exit codes: 0 merged, 1 refused, 2 empty landing, 3 wait, 4 merged but the landing is not yet visible. Each refusal names the next step.
4. `merge_check.py` takes the reasons of the same table (REFUSE as errors, WAIT as warnings) and adds its local file checks. Its stale "no PR CI" note is gone.

5. Area selection (Wave 4, item 2): a change to `tests/conftest.py`, `tests/areas.py`, `tests/area_floors.json`, `tests/*_support.py` or `tests/*_plants.py` selects every area, and `tools/select_areas.py` reads the diff with `--no-renames`, so a rename lists both paths. A BLOCKED merge state with green checks is WAIT (GitHub lags a few seconds), not REFUSE.

**Rejected.** Deleting `merge_check.py` (owner: it stays); a second table in each tool.

**Tests.** `tests/test_merge_pr.py` (every row, the exit codes, `--json`, `--wait`), `tests/test_merge_check.py`.
