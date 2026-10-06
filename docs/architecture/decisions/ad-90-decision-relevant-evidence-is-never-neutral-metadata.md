# AD-90 Decision-relevant evidence is never neutral metadata

Evidence used to decide a result is semantic, even when called metadata. Baseline roles can suppress
an unused-interface finding, so role-only changes must remain visible under `--against`. Reject
unclassified baseline fields rather than let them influence validation.

Multiple paths to one proven origin are not ambiguity. UNKNOWN remains separate from decided
evidence; scoped PASS now follows [AD-124](ad-124-rule-pass-requires-complete-scope-receipt.md).
Proof: [test_widening.py](../../../tests/test_widening.py) and
[test_baseline.py](../../../tests/test_baseline.py).
