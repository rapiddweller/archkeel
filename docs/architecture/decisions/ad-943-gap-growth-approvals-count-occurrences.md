# AD-943 Gap growth approvals count occurrences

**Status.** Accepted. Amends AD-672 and AD-733.

**Reason.** One growth entry previously approved any number of identical new gaps. A removed
occurrence could also return while another occurrence kept the entry live.

**Decision.** Each gap growth entry approves one occurrence. When a gap count grows, the growth
file must hold a reasoned entry for every occurrence of that gap in the new pin. Check mode marks
entries above the pinned count stale. `--write` removes those entries when the pin shrinks.
Both `--write` and the base comparison apply the same count.

**Rejected.** Reusing one entry for every identical gap: it permits unreviewed growth.

**Limit.** Growth of an existing gap without entries requires entries for its existing occurrences
as well as its new occurrences. Existing pins and growth files do not need migration.

**Tests.** `tests/test_native_expected_gaps.py` checks growth, base comparison, removal and return.
