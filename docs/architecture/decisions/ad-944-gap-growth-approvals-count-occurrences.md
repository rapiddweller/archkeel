# AD-944 Gap growth approvals count occurrences

**Status.** Accepted. Amends AD-672 and AD-733.

**Reason.** One growth entry previously approved any number of identical new gaps. A removed
occurrence could also return while another occurrence kept the entry live.

**Decision.** Each new gap occurrence needs a new reasoned entry. The comparison uses the pin and
growth file from the same Git merge base. Check mode marks entries above the pinned count stale.
`--write` removes those entries when the pin shrinks. For gap growth, `--write` requires
`--base-ref` with both files committed. Commit an intermediate pin before later growth.

**Rejected.** Reusing one entry for every identical gap: it permits unreviewed growth.

**Limit.** The check compares committed states. It cannot identify a removal and return inside
one uncommitted change. Commit the removal before assessing the return.

**Tests.** `tests/test_native_expected_gaps.py` checks growth, base comparison, removal and return.

**Superseded in part.** AD-1061: the count by occurrence moves to `tools/self_check_diff.py` (AD-1061).
