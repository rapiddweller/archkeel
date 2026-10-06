# AD-80 `string_literal_compare` follows proven local string constants

`string_literal_compare` follows module/class names bound exactly once to string literals. `Final`
alone proves nothing; enum members are the intended typed vocabulary and remain excluded. Imported,
conditional, reassigned and dynamic values stay unknown.

Replacing a literal with an untyped local constant must not hide the same vocabulary. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).
