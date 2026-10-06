# AD-76 `boundary_types` and `symbol_placement` are restrictions in `--against`

Treat `boundary_types` and `symbol_placement` as restrictions under `--against`: adding narrows;
removing widens and requires an exact amendment. Check the permission/restriction partition against
the typed rule union rather than duplicate its inventory.

Unknown runtime kinds still fail closed as widening. Proof:
[test_widening.py](../../../tests/test_widening.py).
