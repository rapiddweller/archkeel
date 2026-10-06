# AD-99 Facade and coupling budgets are contract ceilings

Facade and directed coupling budgets set explicit ceilings with provenance. Baselines store accepted
name sets, catching swaps that counts miss. Without a baseline, excess exits two; with one,
additions require acceptance and removals must be recorded. Undecidable budgets always exit two.

Count only proven exports and crossings. Pair budgets require type-checking-inclusive interface
policy so bypasses are violations. Raising/removing ceilings or growing accepted sets widens; Dart
budgets are unsupported.

Proof: [test_facade_budgets.py](../../../tests/test_facade_budgets.py).
