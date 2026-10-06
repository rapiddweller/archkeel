# AD-126 Target ranking retains four unresolved stdlib calls

Use the standard-library `graphlib.TopologicalSorter` for Target dependency order.
Retain its unresolved receiver calls as analysis limits rather than implement
another sorter or pretend those calls are resolved.

A reviewed baseline amendment accepts the added count. Acceptance changes neither
analyzer behavior nor violation policy, and successful validation cannot prove
full call resolution or architectural PASS.

[Approved amendment](ad-126-ranking-budget-amendment.json) and
[Target graph proof](../../../tests/test_target_graph.py).
