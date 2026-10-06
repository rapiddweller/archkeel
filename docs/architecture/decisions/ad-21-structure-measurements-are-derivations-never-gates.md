# AD-21 Structure measurements are derivations, never gates

Derive component and package structure measurements from the existing observation. They support
review, not a combined quality score or an implicit conformance gate. Missing inputs must remain
visible rather than yielding fabricated zeroes.

Explicit validation budgets are separate decisions:
[AD-89](ad-89-selected-measurements-share-the-validation-baseline.md) and
[AD-99](ad-99-facade-and-coupling-budgets-are-contract-ceilings.md). Proof:
[test_structure.py](../../../tests/test_structure.py).
