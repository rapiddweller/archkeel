# AD-52 A violation is named by what it is, and a baseline may hold the ones already there

Baseline violations by sorted rule IDs and subjects, with occurrence counts; positions and
evidence-linked IDs are not identity. Validation requires exact counts: new debt and resolved debt
both fail until reviewed or recorded. Baselines never hide violations or turn declared-rule FAIL
into PASS.

Only `rule.violated` is baselineable. Shared subjects cannot identify individual occurrences; moves
change identity. Proof: [test_baseline.py](../../../tests/test_baseline.py).
