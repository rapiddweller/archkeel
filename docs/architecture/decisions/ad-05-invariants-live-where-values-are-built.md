# AD-5 Invariants live where values are built

Enforce dependent-field invariants in constructors. For example, completeness must agree with
diagnostics, and a supported measurement must carry a value. Invalid objects should fail at
creation; `assert` is unsuitable because optimized Python removes it.

Proof: [test_model.py](../../../tests/test_model.py) and
[test_diagnostics.py](../../../tests/test_diagnostics.py).
