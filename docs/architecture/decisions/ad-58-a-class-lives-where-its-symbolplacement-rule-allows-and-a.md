# AD-58 A class lives where its symbol_placement rule allows, and a facade's dict or object is all boundary_types decides

Use `symbol_placement` for declared class-kind placement and `boundary_types` for scoped facade
types. A provider-owned boundary model is valid even when the consumer belongs to another component.
Do not exempt every model or apply facade policy to legitimate codec internals.

[AD-63](ad-63-boundarytypes-reads-a-components-declared-public-list-not-a.md) replaces the original
naming-based facade selection; later boundary decisions extend resolution. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).
