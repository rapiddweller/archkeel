# AD-61 A widening fails unless an amendment binds its exact before and after digest

`validate --against` rejects contract or baseline widening with exit one unless an amendment binds
the exact before/after policy: recursively mounted contracts and baseline roles, counts and budgets.
Unmodeled changes fail closed. Require a decider and rationale; explicit stale amendments fail even
without widening. Invalid comparison evidence exits two.

Approval covers the whole pair without expiry; attribution is unauthenticated.
[AD-103](ad-103-baseline-and-amendment-paths-are-relative-to-root.md) requires root-contained policy
paths; [AD-104](ad-104-a-contract-the-compared-revision-lacks-is-introduced.md) binds absent
contracts to their path. Legacy amendments remain readable for contract-only comparisons.

Proof: [test_widening.py](../../../tests/test_widening.py).
