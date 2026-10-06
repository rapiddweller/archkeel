# AD-6 A function has one responsibility

A function over 80 lines, including nested functions, needs a named allowance and reason. Extract a
helper only for a real phase or invariant, not to satisfy the counter. Keep allowances keyed by path
and qualified name; reject both unlisted long functions and stale exemptions.

Proof: [test_repository_hygiene.py](../../../tests/test_repository_hygiene.py).
