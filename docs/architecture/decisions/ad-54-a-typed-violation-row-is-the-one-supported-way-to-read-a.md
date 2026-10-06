# AD-54 A typed violation row is the one supported way to read a report's violations, and `ir.baseline` derives it once for everything that groups them

Derive one typed `ViolationRow` per violation and reuse it for baselines and grouped counts. Keep
rule IDs and subjects on the fingerprint; absent kind-specific values are `None`. Reject malformed
empty rule lists at decoding instead of hiding them downstream.

The original codec file-read path was replaced by
[AD-64](ad-64-archkeelapi-is-the-declared-external-contract-and-ir.md)'s external facade. Proof:
[test_violations.py](../../../tests/test_violations.py).
