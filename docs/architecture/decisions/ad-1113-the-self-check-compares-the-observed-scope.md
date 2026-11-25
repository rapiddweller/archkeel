# AD-1113 The self-check compares the observed scope

**Status.** Accepted. Amends AD-1061 and AD-1064.

**Decision.** The native gate keeps the scanned paths and component scopes from the core topology.
It compares them with the base as one grown item. It also compares the root contract digest.
Thus, every root contract edit needs approval, even one that changes only text.
When contract inputs change and gaps disappear, the gate counts one grown item.
The inputs include contract files and their provenance documents.

The gate refuses a result without complete module and component rows.
It recomputes a cached `selfcheck-v1` base with the old core and `report --topology`.
The new condensed format is `selfcheck-v2`. A base that cannot be recomputed needs approval.

**Reason.** A contract can narrow a component without changing the scanned paths or their count.
It can remove gaps while the old gate reports `grown 0`. A path swap can also keep the count.
The topology already carries the paths, ownership and component scopes. The gate checks the
topology totals before it uses those rows, because the display has size limits.

**Rejected.** A path count cannot detect a swap. A path hash alone cannot detect a contract edit.
Reimplementing contract scope in the gate would duplicate the core's model.

**Limit.** A change to a provenance document counts as growth when gaps also disappear.
An inside-contract edit that changes no observed component scope and removes no gap is not seen.
The count-bound approval of AD-1061 still applies.

**Tests.** `tests/test_self_check_gate.py` uses a real core and a real git repository.
It narrows a component while the scanned paths stay equal. It also checks path swaps, incomplete
topology, legacy cache invalidation and changed contract inputs with removed gaps.
