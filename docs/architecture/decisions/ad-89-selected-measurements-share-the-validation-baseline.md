# AD-89 Selected measurements share the validation baseline

Selected measurement budgets share the violation baseline and its write path. Require complete
evidence and exact accepted values: rises need explicit acceptance; falls must be recorded. Missing
measurements never become PASS.

Raising or dropping accepted values, or removing declarations, widens under `--against`; adding a
declaration narrows. Only supported profile measurements qualify. Proof:
[test_measurement_budgets.py](../../../tests/test_measurement_budgets.py).
