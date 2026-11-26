# AD-1128 Compare the observed scan scope, not the whole contract

**Status.** Accepted. Amends AD-1113.

**Decision.** Compare the scanned paths, module ownership, component identities and component
scope. Compare the `[scan]` table as before. Do not count the contract digest, public items,
planned public items or component layer as scan scope. The condensed result keeps these fields
for validation and same-commit comparison. When contract inputs change and gaps disappear,
the existing growth check still applies.

The summary reads the same scan table as the gate. Both use the same growth comparison.

**Reason.** Public items and dependency declarations do not change which files a component
owns. Their edits must not need scope approval when the observed scope and gaps stay unchanged.
The old summary compared a missing scan table against the base table.

**Rejected.** Compare the whole contract digest: it reports unrelated edits as scope changes.
Compare only file counts: a path swap or narrowed component can keep the same count.

**Limit.** The comparison detects the scope represented by the complete core topology.
It does not prove that the core topology itself is correct. A changed contract input that
removes gaps still needs approval, even when the observed scope does not change.

**Tests.** `tests/test_self_check_gate.py` checks a narrowed component with the real core and
path swaps. `tests/test_self_check_scope.py` checks public items, dependency declarations and
the summary against the gate. `tests/test_self_check_summary.py` checks the scan table.
