# AD-82 A component namespace restricts placement, not ownership

`packages` owns modules; optional component `namespace` restricts their physical placement. Observed
owned modules outside it produce baselineable placement violations. Omitting namespace preserves old
behavior.

Adding the restriction narrows; removing or changing it widens. Reuse module facts instead of
inferring ownership from placement. Proof:
[test_contract_model.py](../../../tests/test_contract_model.py) and
[test_widening.py](../../../tests/test_widening.py).
