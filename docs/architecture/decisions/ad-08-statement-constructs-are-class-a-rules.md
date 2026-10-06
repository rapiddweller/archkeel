# AD-8 Statement constructs are Class A rules

Treat forbidden statements as construct facts, separate from typing measurements. Broad handlers
include bare catches, `Exception`, `BaseException`, tuples and qualified builtins, even when they
re-raise. Exceptions require scoped contract allowances.

Aliases and shadowing remain blind spots. Existing contracts retain their meaning; older versions
reject the added construct syntax with exit two. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).
