# AD-67 An undecidable boundary position is UNKNOWN, not silence

Record undecidable boundary positions explicitly instead of silently passing them. Aggregate counts
by rule and kind, separate from scan coverage; uncertainty is not a violation. Reuse one annotation
walk for known collection elements.

This began with one collection level; later boundary decisions extend supported shapes. Verdict
handling follows [AD-72](ad-72-a-rule-that-could-not-decide-everything-reports-unknown.md) and
[AD-124](ad-124-rule-pass-requires-complete-scope-receipt.md). Proof:
[test_boundary_type_unknown_verdict.py](../../../tests/test_boundary_type_unknown_verdict.py).
