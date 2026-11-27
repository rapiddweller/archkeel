# AD-1260: The self-check gate checks one run and compares nothing

Status: accepted. Owner decision 2026-11-27 (drift-gates audit, step B). Supersedes AD-1061, AD-1064, AD-1145,
AD-1221, AD-1113 and AD-1128, and point 2 of AD-1230.

## Why

The gate compared the self-check result of a PR with the result of the base commit, and asked for the label
`ratchet-lead` for a lost rule or scope. It needed a cache of the base result, a fallback to an earlier main
commit, a computed base when both missed (6 minutes more, and the 15-minute limit), a label read, a rerun, a nightly
comparison and a pile of tests. The head contract cannot detect its own removal, and a gap only holds a rule at
UNKNOWN, so the comparison caught no false PASS that the verdict of the core did not. The live pins in the tests
(three UNKNOWN rule ids, thirteen compiler-only edges, `files > 200`) were the same comparison with yesterday's
answers. The README badge already shows the verdict counts of main.

## Decision

1. `tools/self_check_gate.py` judges one run. It fails only when the result is missing, empty, malformed or a refusal;
   when a status is not PASS, FAIL or UNKNOWN; when the core reports a FAIL or a violation; when the counted
   violations differ from the listed ones; or when the exit code is not the one that the statuses give. An UNKNOWN
   rule and a gap never fail it, and never turn into a PASS. The shell check uses the same gate (no zero-gap policy).
2. Deleted: `tools/self_check_diff.py`, `self_check_contract.py`, `self_check_shell.py`, the label `ratchet-lead`,
   the saved base result (the `selfcheck-v1/v2` caches), the fallback to earlier main commits, the computed base,
   the nightly comparison with the gate-profile result, `grown.txt`, the label read, and their tests and fixtures.
   Build caches stay.
3. Deleted: the pins of the live self run in `tests/core_support.py` (`NATIVE_UNKNOWN`, `NATIVE_COMPILER_ONLY_EDGES`,
   `NATIVE_SELF_STATUS`, `SHELL_SELF_STATUS`) and their callers. The tests now require a usable result without FAIL
   or violation, and the paired compiler / no-compiler evidence tests on contrived inputs stay.
4. `make self-check` still prints at most 40 lines: verdicts, violations, UNKNOWN causes, size, hotspots and cycles.

## What still covers each removed check

| Removed | Real defect | Still covered by |
|---|---|---|
| Rule removed or worse than on the base | A PR hides a violation by deleting a rule | The contract change is in the PR diff and gets review (Codex and the lead). Nothing else: owner decision. |
| Scope shrank or changed | A scan silently reads fewer files | `NATIVE-ASSIGNMENT-COMPLETE` and the rule `complete_assignment` of the core; the README badge shows the counts of main. |
| New UNKNOWN reason | A rule goes UNKNOWN for a new cause | Shown in `make self-check` (UNKNOWN causes). An UNKNOWN is never a PASS. None as a gate: owner decision. |
| Gap growth | The scan gets less precise | Shown as the gap count in the log and in the badge; none as a gate: owner decision. |
| Shell zero-gap policy | A shell gap hides a violation | The core holds each affected rule at UNKNOWN; none as a gate: owner decision. |
| Rule ids equal the contract | A rule is missing from the result | `problems()`: a result without rules is red; the core decides each rule of the contract it read. |
| Live pins in tests | Yesterday's answer drifts | The paired evidence tests on contrived inputs, and the gate on the real run. |
| Nightly gate-profile versus release result | The release core differs from the gate core | The release tests and the wheel checks (`smoke_test`, wheel tests). |

## Not done yet

`ready.sh` of the lead reads the line `self-check diff: grown N` for its gap-growth line: it prints `unknown` now.
The README badge is the place for counts; a gap count in the badge is a later step.
