# AD-19 Words for people are plain; identifiers for machines stay stable

Use NOT CHECKED when a required check did not run or lacked evidence. Keep machine keys, enum values
and diagnostic codes stable; translate only human presentation. A friendly headline must not turn
missing evidence into PASS.

Proof: [test_terminal.py](../../../tests/test_terminal.py) and
[test_validation.py](../../../tests/test_validation.py).
