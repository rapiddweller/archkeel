# AD-86 Root layout allows only declared immediate children

`root_layout` allows only declared immediate children of a root. Reject root-self, nested and
foreign entries. Ignore the root module; absent allowed children are not findings. Unexpected
observed children produce baselineable violations.

Adding a child widens and removing one narrows; adding the restriction narrows and removing it
widens. Reuse existing module/package facts. Proof:
[test_contract_model.py](../../../tests/test_contract_model.py).
