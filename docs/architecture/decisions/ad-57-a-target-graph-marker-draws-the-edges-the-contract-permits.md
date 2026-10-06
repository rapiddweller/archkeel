# AD-57 A target graph marker draws the edges the contract permits

Keep observed and target graphs under separate markers. The target graph draws permitted pairs from
`requires` and `allowed_dependency`; the observed graph retains actual edges and violations. With
neither permission model, the target set is empty.

Parity proves agreement with the contract, not code conformance. Coarse pairs omit narrower
symbol/source restrictions. Safe rewriting follows
[AD-46](ad-46-validate-writegraph-regenerates-the-marked-component-graph.md). Proof:
[test_validation.py](../../../tests/test_validation.py).
