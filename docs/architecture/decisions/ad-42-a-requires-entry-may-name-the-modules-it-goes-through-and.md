# AD-42 A `requires` entry may name the modules it goes through, and twelve prohibitions become that one permission

A `requires` entry may narrow its target through module prefixes. The target still owns its symbols;
`through` is an import-path restriction, not a symbol selector or another component. Invalid or
unseen references must fail validation.

This permits a small provider boundary without granting every internal module. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).
