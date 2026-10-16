# AD-48 Reflection that writes, and a value compared with a string literal, are decided, not only reviewed

Record reflection constructs and string comparisons as syntax facts. Comparisons,
membership with a supported literal needle or literal collection, and match cases
count in every expression position. The parser/protocol scope in #542 includes
text/bytes needles on the left of `in`/`not in` and Python's `__main__` entry
check; these extend the original literal-collection scope and entry-check exclusion.

Typed control boundaries use owned vocabularies. Aliases and runtime behavior
remain outside the proof: a syntax observation does not infer arbitrary data or
an imported runtime value to be a string.

`getattr` and `hasattr` remain typing signals.
[AD-80](ad-80-string-constant-comparisons-are-statically-resolved.md) adds proven local string
constants. The same bounded scalar evidence applies to membership needles.
See [native comparison coverage](../string-comparison-observation.md) and
[test_analyzer.py](../../../tests/test_analyzer.py).
