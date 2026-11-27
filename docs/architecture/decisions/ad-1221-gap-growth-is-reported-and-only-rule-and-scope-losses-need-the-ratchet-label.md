# AD-1221 Gap growth is reported, and only rule and scope losses need the ratchet label

**Status.** Accepted. Owner decision of 2026-11-27 after two gate reviews. Supersedes the growth part of Superseded by [AD-1260](ad-1260-the-self-check-gate-checks-one-run-and-compares-nothing.md): the self-check compares nothing.
[AD-1061](ad-1061-the-self-check-is-compared-with-its-base-commit-beside-the-pins.md) (point 4) and
[AD-944](ad-944-gap-growth-approvals-count-occurrences.md).

**Reason.** A new gap makes a rule UNKNOWN (exit 2) and never PASS. Counting gaps did not protect soundness:
all growth was approved, and in the last 200 PR gate runs 35 of the 45 newest failures held a ratchet
approval FAIL. Each one cost an edit of the PR text and a gate run of 12 to 15 minutes.

**Decision.**
1. A new gap passes. The log and the step summary show one line `gap growth: N items (top kinds ...)`. The
   items are in `grown.txt`. The lead reads the line.
2. These items still fail without the label `ratchet-lead`: a removed rule, a rule with a worse status,
   a new UNKNOWN reason kind, fewer scanned files, a changed `[scan]` table or scope, changed contract
   inputs with removed gaps, and an unusable base. `absolute()` is unchanged: a refusal, a FAIL, a violation
   or a false exit code has no approval path.
3. The label alone approves. The line `Ratchet growth: <N> items: <reason>` and the line
   `Ratchet growth (shell): ...` are gone, and no tool reads the PR text. The shell gate asks the label for a
   removed rule.
4. A body edit starts nothing. After the label the lead runs the gate again by hand (AD-1223 deleted the rerun workflow).

**Counter-example.** A gap cannot produce a PASS: the core holds the affected rules at UNKNOWN and the
exit code of the result is 2 (`absolute()` checks it). The tests `test_a_new_gap_...` run this on the real
result.

**Rejected.** A digest of the approved items bound to PR, head and base (review of 2026-11-27): it keeps the
rerun for each correction and guards no soundness. A cap on the count: the count says nothing about
soundness.

**Limit.** "Top kinds" names the gap kinds. A gap subject has no common module field. A growth that hides
a lost check inside a gap reason is not seen by this gate. Codex review and the counter-example run stay.

**Tests.** `tests/test_self_check_diff.py`, `tests/test_self_check_shell.py`,
`tests/test_self_check_gate.py`, `tests/test_native_ci.py`.
