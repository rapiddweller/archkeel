# AD-39 An empty `selected_changes` declares that nothing architectural changed

An empty change selection declares no semantic change and rejects changes in every dimension. A
nonempty selection checks selected fingerprints and required guardrails; unselected changes outside
those guardrails remain admitted. Guardrails must remain independent of selected improvements.

[AD-44](ad-44-an-undeclared-added-dependency-edge-is-a-guardrail-failure.md) defines new-edge and
regression handling. Proof: [test_expectation.py](../../../tests/test_expectation.py).
