# AD-1128 Compare the contract without cosmetic JSON changes

**Status.** Accepted. Amends AD-1113. Superseded by [AD-1260](ad-1260-the-self-check-gate-checks-one-run-and-compares-nothing.md): the self-check compares nothing.

**Decision.** Compare all contract fields, scanned paths, module ownership and component
scope. Compare the `[scan]` table as before. Normalize JSON whitespace, object key order and
component order. Keep array order for all other fields. Include every inside contract.
Verify the recorded digest before reading a contract. If either contract is unavailable,
compare all recorded input digests on both sides. This fallback can report cosmetic changes
as growth. An offline `BASE_RESULT` can supply the base without a local base ref.

The existing v2 cache carries the raw digest and input paths. The gate reads the base contract
from that commit and normalizes it without a new scan. The summary uses the gate's results
and the same growth comparison. Changed contract inputs and removed gaps still count.

**Reason.** A public item, dependency, layer or rule can change a verdict. Even rationale and
responsibility text affect contract hygiene. None of these fields is safe to ignore.
The old summary compared a missing scan table against the base table.

**Rejected.** Compare only paths and ownership: it allows a changed rule to hide a violation.
Compare raw JSON bytes: it counts whitespace and key order as scope changes.

**Limit.** The fallback also counts changes to provenance documents. The comparison does
not prove that the core topology is correct. A v1 cache still uses the AD-1113 migration limit.

**Tests.** `tests/test_self_check_gate.py` checks a narrowed component with the real core and
path swaps. `tests/test_self_check_scope.py` checks layer changes, rule order, public items,
dependency declarations, cosmetic JSON changes and the summary against the gate.
