# AD-81 The project owns one fail-closed Make gate

The repository owns one fail-closed Make gate. Archkeel does not infer project commands or add
generic test-policy configuration. Reuse validation, against comparison and locked release checks;
with a base comparison, do not validate head twice.

Make must stop dependent stages on failure, including parallel invocations. CI adds browser and
renderer acceptance. Proof: [test_make_gate.py](../../../tests/test_make_gate.py) and
[Makefile](../../../Makefile).
