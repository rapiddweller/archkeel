# AD-72 A rule that could not decide everything reports UNKNOWN

Declared-rule uncertainty must reach the verdict: violations outrank UNKNOWN, which outranks PASS.
Keep external-type uncertainty measured separately because no provider component/public contract
governs it; do not disguise it as decided evidence.

Standing collection limits are not automatically contract uncertainty.
[AD-124](ad-124-rule-pass-requires-complete-scope-receipt.md) now requires complete scoped receipts
for PASS. Proof:
[test_boundary_type_unknown_verdict.py](../../../tests/test_boundary_type_unknown_verdict.py).
