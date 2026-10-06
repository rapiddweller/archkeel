# AD-48 Reflection that writes, and a value compared with a string literal, are decided, not only reviewed

Record reflection constructs and string comparisons as syntax facts. Comparisons, literal-collection
membership and match cases count in every expression position; exclude only Python's `__main__`
entry check. Scoped exemptions protect legitimate boundaries. Aliases and runtime behavior remain
outside the proof.

`getattr` and `hasattr` remain typing signals.
[AD-80](ad-80-string-constant-comparisons-are-statically-resolved.md) adds proven local string
constants. Proof: [test_analyzer.py](../../../tests/test_analyzer.py).
