# AD-32 A component names what it requires; what it does not name is forbidden

A component's complete `requires` list permits named outward targets and forbids omitted ones. An
absent list leaves intent open. `init` proposes from observation but does not approve it.

Source, symbol and `through` restrictions still narrow permitted targets; requirements retain
rationale and attribution. Proof: [test_analyzer.py](../../../tests/test_analyzer.py) and
[test_contract_model.py](../../../tests/test_contract_model.py).
