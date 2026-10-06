# AD-70 The external promise declares every type it hands out

Expose `load_violations` returning typed rows, without leaking internal `Observation` through
composed public calls. Declare every type the facade hands out, including the fingerprint. One
load-and-derive entry avoids promising internal IR or duplicating identity fields.

The replaced facade was unreleased, so no published promise was broken. Proof:
[test_violations.py](../../../tests/test_violations.py).
